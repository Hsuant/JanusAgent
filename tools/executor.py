"""代码执行器。

基于 Jupyter 内核提供代码执行能力，支持状态持久化。
"""

import asyncio
import logging
import time
import uuid
from queue import Empty
from typing import Any, Dict, List, Optional

from jupyter_client import KernelManager
from jupyter_client.kernelspec import find_kernel_specs

from tools.config import ExecutorConfig, get_config
from tools.exceptions import ExecutionError
from tools.utils import ensure_dir

logger = logging.getLogger(__name__)


class KernelSession:
    """Jupyter 内核会话。

    Attributes:
        session_id: 会话 ID。
        kernel_manager: 内核管理器。
        client: 内核客户端。
        created_at: 创建时间。
        last_used: 最后使用时间。
    """

    def __init__(self, session_id: str, kernel_manager: KernelManager) -> None:
        self.session_id = session_id
        self.kernel_manager = kernel_manager
        self.client = kernel_manager.client()
        self.created_at = time.time()
        self.last_used = time.time()
        self._channels_started = False

    def ensure_channels(self) -> None:
        """启动客户端通道。"""
        if not self._channels_started:
            self.client.start_channels()
            self.client.wait_for_ready()
            self._channels_started = True

    def shutdown(self) -> None:
        """关闭会话。"""
        try:
            if self._channels_started:
                self.client.stop_channels()
            self.kernel_manager.shutdown_kernel(now=True)
        except Exception as e:
            logger.warning("关闭会话 %s 时出错: %s", self.session_id, e)


class CodeExecutor:
    """代码执行器。

    管理 Jupyter 内核池，提供代码执行功能。

    Attributes:
        config: 执行器配置。
        _sessions: 会话字典。
        _lock: 异步锁。
    """

    def __init__(self, config: Optional[ExecutorConfig] = None) -> None:
        """初始化代码执行器。

        Args:
            config: 执行器配置。

        Raises:
            ExecutionError: 内核不可用时抛出。
        """
        self.config = config or get_config().executor
        ensure_dir(self.config.workspace_path)

        self._sessions: Dict[str, KernelSession] = {}
        self._lock = asyncio.Lock()

        # 验证内核
        available = find_kernel_specs()
        if self.config.kernel_name not in available:
            raise ExecutionError(
                f"内核 {self.config.kernel_name} 不可用，可用内核: {list(available.keys())}",
                "executor",
            )

        logger.info("代码执行器初始化完成，内核: %s", self.config.kernel_name)

    async def _cleanup_expired(self) -> None:
        """清理过期会话。"""
        now = time.time()
        expired = [
            sid for sid, sess in self._sessions.items()
            if now - sess.last_used > self.config.session_timeout
        ]
        for sid in expired:
            async with self._lock:
                sess = self._sessions.pop(sid, None)
                if sess:
                    sess.shutdown()
                    logger.info("已清理过期会话: %s", sid)

    async def get_session(self, session_id: Optional[str] = None) -> str:
        """获取或创建会话。

        Args:
            session_id: 会话 ID。

        Returns:
            str: 会话 ID。
        """
        await self._cleanup_expired()

        async with self._lock:
            if session_id and session_id in self._sessions:
                self._sessions[session_id].last_used = time.time()
                return session_id

            # 达到上限时清理最旧的
            if len(self._sessions) >= self.config.max_sessions:
                oldest = min(
                    self._sessions.keys(),
                    key=lambda k: self._sessions[k].last_used,
                )
                old = self._sessions.pop(oldest)
                old.shutdown()
                logger.info("已达最大会话数，已清理: %s", oldest)

            new_id = session_id or f"kernel_{uuid.uuid4().hex[:8]}"
            km = KernelManager(kernel_name=self.config.kernel_name)
            km.start_kernel(cwd=self.config.workspace_path)
            session = KernelSession(new_id, km)
            session.ensure_channels()
            self._sessions[new_id] = session
            logger.info("已创建内核会话: %s", new_id)
            return new_id

    async def execute(
        self,
        code: str,
        session_id: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """执行代码。

        Args:
            code: Python 代码。
            session_id: 会话 ID。
            timeout: 超时时间（秒）。

        Returns:
            Dict: 执行结果。

        Raises:
            ExecutionError: 执行失败时抛出。
        """
        timeout = timeout or self.config.execution_timeout
        session_id = await self.get_session(session_id)

        async with self._lock:
            session = self._sessions[session_id]
            session.last_used = time.time()
            session.ensure_channels()

        client = session.client
        msg_id = client.execute(code)

        stdout: List[str] = []
        stderr: List[str] = []
        start_time = time.time()

        while True:
            if time.time() - start_time > timeout:
                try:
                    client.interrupt_kernel()
                except Exception:
                    pass
                stderr.append(f"执行超时（{timeout} 秒）")
                break

            try:
                msg = client.get_iopub_msg(timeout=0.1)
                msg_type = msg.get("msg_type")
                content = msg.get("content", {})

                if msg_type == "stream":
                    text = content.get("text", "")
                    if content.get("name") == "stderr":
                        stderr.append(text)
                    else:
                        stdout.append(text)
                elif msg_type == "error":
                    stderr.append(f"{content.get('ename')}: {content.get('evalue')}")
                    for line in content.get("traceback", []):
                        stderr.append(line)
                elif msg_type == "execute_result":
                    data = content.get("data", {})
                    if "text/plain" in data:
                        stdout.append(data["text/plain"])
                elif msg_type == "status" and content.get("execution_state") == "idle":
                    break
            except Empty:
                continue
            except Exception as e:
                stderr.append(f"消息处理错误: {e}")
                break

        try:
            client.get_shell_msg(timeout=1)
        except Exception:
            pass

        return {
            "success": len(stderr) == 0,
            "stdout": stdout,
            "stderr": stderr,
            "session_id": session_id,
        }

    async def execute_sync(self, code: str, **kwargs) -> Dict[str, Any]:
        """同步风格的异步执行方法（别名）。"""
        return await self.execute(code, **kwargs)

    def execute_blocking(
        self,
        code: str,
        session_id: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """同步执行代码（阻塞方式）。

        Args:
            code: Python 代码。
            session_id: 会话 ID。
            timeout: 超时时间。

        Returns:
            Dict: 执行结果。
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                raise RuntimeError("在运行中的事件循环里无法使用同步方法")
            return loop.run_until_complete(self.execute(code, session_id, timeout))
        except RuntimeError:
            return asyncio.run(self.execute(code, session_id, timeout))

    async def restart_session(self, session_id: str) -> bool:
        """重启指定会话。

        Args:
            session_id: 会话 ID。

        Returns:
            bool: 是否成功。
        """
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False
            try:
                session.kernel_manager.restart_kernel(now=True)
                session._channels_started = False
                session.ensure_channels()
                session.last_used = time.time()
                logger.info("已重启会话: %s", session_id)
                return True
            except Exception as e:
                logger.error("重启会话失败: %s", e)
                return False

    async def close_session(self, session_id: str) -> bool:
        """关闭指定会话。

        Args:
            session_id: 会话 ID。

        Returns:
            bool: 是否成功。
        """
        async with self._lock:
            session = self._sessions.pop(session_id, None)
            if session:
                session.shutdown()
                logger.info("已关闭会话: %s", session_id)
                return True
            return False

    async def close_all(self) -> None:
        """关闭所有会话。"""
        async with self._lock:
            for session in self._sessions.values():
                session.shutdown()
            self._sessions.clear()
            logger.info("所有代码执行会话已关闭")

    async def __aenter__(self) -> "CodeExecutor":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close_all()


# 便捷函数
async def execute_code(code: str, **kwargs) -> Dict[str, Any]:
    """便捷异步函数：执行代码。"""
    async with CodeExecutor() as executor:
        return await executor.execute(code, **kwargs)


def execute_code_sync(code: str, **kwargs) -> Dict[str, Any]:
    """便捷同步函数：执行代码。"""
    executor = CodeExecutor()
    try:
        return executor.execute_blocking(code, **kwargs)
    finally:
        asyncio.run(executor.close_all())