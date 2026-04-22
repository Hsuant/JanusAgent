"""Jupyter 内核管理器。

提供 Jupyter 内核的生命周期管理，支持代码执行、状态持久化和超时控制。
"""

import asyncio
import logging
import time
import uuid
from queue import Empty
from typing import Any, Dict, List, Optional, Tuple

from jupyter_client import KernelManager
from jupyter_client.kernelspec import find_kernel_specs

logger = logging.getLogger(__name__)


class KernelSession:
    """内核会话。

    封装单个 Jupyter 内核的连接信息和状态。

    Attributes:
        session_id: 会话唯一标识符。
        kernel_manager: Jupyter 内核管理器实例。
        client: 内核客户端，用于执行代码。
        created_at: 会话创建时间戳。
        last_used: 最后使用时间戳。
    """

    def __init__(self, session_id: str, kernel_manager: KernelManager) -> None:
        """初始化内核会话。

        Args:
            session_id: 会话唯一标识符。
            kernel_manager: Jupyter 内核管理器实例。
        """
        self.session_id = session_id
        self.kernel_manager = kernel_manager
        self.client = kernel_manager.client()
        self.created_at = time.time()
        self.last_used = time.time()
        self._channels_started = False

    def ensure_channels(self) -> None:
        """确保客户端通道已启动。"""
        if not self._channels_started:
            self.client.start_channels()
            self.client.wait_for_ready()
            self._channels_started = True
            logger.debug("会话 %s 的客户端通道已启动", self.session_id)

    def shutdown(self) -> None:
        """关闭会话，释放资源。"""
        try:
            if self._channels_started:
                self.client.stop_channels()
            self.kernel_manager.shutdown_kernel(now=True)
            logger.debug("会话 %s 已关闭", self.session_id)
        except Exception as e:
            logger.warning("关闭会话 %s 时出错: %s", self.session_id, e)


class JupyterKernelManager:
    """Jupyter 内核管理器。

    管理多个内核会话，提供代码执行、状态持久化等功能。

    Attributes:
        workspace_path: 工作空间路径。
        kernel_name: 内核名称，默认为 "python3"。
        max_sessions: 最大会话数。
        session_timeout: 会话超时时间（秒）。
        execution_timeout: 代码执行超时时间（秒）。
    """

    def __init__(
        self,
        workspace_path: str = "/opt/workspace",
        kernel_name: str = "python3",
        max_sessions: int = 10,
        session_timeout: int = 3600,
        execution_timeout: int = 30,
    ) -> None:
        """初始化 Jupyter 内核管理器。

        Args:
            workspace_path: 工作空间路径。
            kernel_name: 内核名称。
            max_sessions: 最大会话数。
            session_timeout: 会话超时时间（秒）。
            execution_timeout: 代码执行超时时间（秒）。
        """
        self.workspace_path = workspace_path
        self.kernel_name = kernel_name
        self.max_sessions = max_sessions
        self.session_timeout = session_timeout
        self.execution_timeout = execution_timeout

        self._sessions: Dict[str, KernelSession] = {}
        self._lock = asyncio.Lock()

        # 验证内核是否可用
        available_kernels = find_kernel_specs()
        if kernel_name not in available_kernels:
            logger.warning(
                "内核 %s 不可用，可用内核: %s",
                kernel_name,
                list(available_kernels.keys())
            )
        else:
            logger.info("Jupyter 内核管理器初始化完成，内核: %s", kernel_name)

    async def _cleanup_expired_sessions(self) -> None:
        """清理过期的会话。"""
        current_time = time.time()
        expired_sessions = [
            session_id
            for session_id, session in self._sessions.items()
            if current_time - session.last_used > self.session_timeout
        ]

        for session_id in expired_sessions:
            async with self._lock:
                session = self._sessions.pop(session_id, None)
                if session:
                    session.shutdown()
                    logger.info("已清理过期会话: %s", session_id)

    async def get_or_create_kernel(self, session_id: Optional[str] = None) -> str:
        """获取或创建内核会话。

        Args:
            session_id: 会话标识符，如果为 None 则创建新会话。

        Returns:
            str: 会话标识符。
        """
        await self._cleanup_expired_sessions()

        async with self._lock:
            # 如果提供了 session_id 且会话存在，则返回
            if session_id and session_id in self._sessions:
                session = self._sessions[session_id]
                session.last_used = time.time()
                logger.debug("复用已有会话: %s", session_id)
                return session_id

            # 检查会话数量是否达到上限
            if len(self._sessions) >= self.max_sessions:
                # 清理最旧的会话
                oldest_session_id = min(
                    self._sessions.keys(),
                    key=lambda sid: self._sessions[sid].last_used
                )
                old_session = self._sessions.pop(oldest_session_id)
                old_session.shutdown()
                logger.info("已达到最大会话数，已清理最旧会话: %s", oldest_session_id)

            # 创建新会话
            new_session_id = session_id or f"kernel_{uuid.uuid4().hex[:8]}"
            kernel_manager = KernelManager(kernel_name=self.kernel_name)
            kernel_manager.start_kernel(cwd=self.workspace_path)

            session = KernelSession(new_session_id, kernel_manager)
            session.ensure_channels()
            self._sessions[new_session_id] = session

            logger.info("已创建新内核会话: %s", new_session_id)
            return new_session_id

    async def execute_code(
        self,
        code: str,
        session_id: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """执行代码。

        Args:
            code: 要执行的代码。
            session_id: 会话标识符。
            timeout: 执行超时时间（秒）。

        Returns:
            Dict: 包含执行结果的字典，格式为：
                {
                    "success": bool,
                    "result": List[str],
                    "error": List[str],
                    "session_id": str,
                    "execution_count": int
                }
        """
        timeout = timeout or self.execution_timeout
        session_id = await self.get_or_create_kernel(session_id)

        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                raise ValueError(f"会话不存在: {session_id}")

            session.last_used = time.time()
            session.ensure_channels()

        # 执行代码（在锁外部进行，避免阻塞其他请求）
        try:
            result, error, execution_count = await self._execute_in_kernel(
                session, code, timeout
            )
            return {
                "success": len(error) == 0,
                "result": result,
                "error": error,
                "session_id": session_id,
                "execution_count": execution_count,
            }
        except Exception as e:
            logger.error("执行代码时出错: %s", e)
            return {
                "success": False,
                "result": [],
                "error": [str(e)],
                "session_id": session_id,
                "execution_count": 0,
            }

    async def _execute_in_kernel(
        self,
        session: KernelSession,
        code: str,
        timeout: int,
    ) -> Tuple[List[str], List[str], int]:
        """在内核中执行代码的内部实现。

        Args:
            session: 内核会话。
            code: 要执行的代码。
            timeout: 超时时间。

        Returns:
            Tuple: (stdout 输出列表, stderr 输出列表, 执行计数)。
        """
        client = session.client
        msg_id = client.execute(code)

        stdout_list: List[str] = []
        stderr_list: List[str] = []
        execution_count = 0
        start_time = time.time()

        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                # 超时，尝试中断执行
                try:
                    client.interrupt_kernel()
                    logger.warning("代码执行超时，已中断内核")
                except Exception as e:
                    logger.error("中断内核失败: %s", e)
                stderr_list.append(f"执行超时（超过 {timeout} 秒）")
                break

            try:
                msg = client.get_iopub_msg(timeout=0.1)
                msg_type = msg.get("msg_type")
                content = msg.get("content", {})

                if msg_type == "stream":
                    stream_name = content.get("name", "stdout")
                    text = content.get("text", "")
                    if stream_name == "stdout":
                        stdout_list.append(text)
                    elif stream_name == "stderr":
                        stderr_list.append(text)

                elif msg_type == "error":
                    error_content = content.get("ename", "")
                    error_value = content.get("evalue", "")
                    error_traceback = content.get("traceback", [])
                    stderr_list.append(f"{error_content}: {error_value}")
                    if error_traceback:
                        stderr_list.extend(error_traceback)

                elif msg_type == "execute_result":
                    data = content.get("data", {})
                    text_plain = data.get("text/plain", "")
                    if text_plain:
                        stdout_list.append(text_plain)
                    execution_count = content.get("execution_count", 0)

                elif msg_type == "status":
                    if content.get("execution_state") == "idle":
                        # 执行完成
                        break

            except Empty:
                continue
            except Exception as e:
                stderr_list.append(f"获取消息时出错: {e}")
                break

        # 等待 shell 回复确认执行完成
        try:
            client.get_shell_msg(timeout=1)
        except Exception:
            pass

        return stdout_list, stderr_list, execution_count

    async def restart_kernel(self, session_id: str) -> bool:
        """重启指定的内核。

        Args:
            session_id: 会话标识符。

        Returns:
            bool: 是否成功重启。
        """
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False

            try:
                session.kernel_manager.restart_kernel(now=True)
                session.last_used = time.time()
                session._channels_started = False
                session.ensure_channels()
                logger.info("已重启内核会话: %s", session_id)
                return True
            except Exception as e:
                logger.error("重启内核失败: %s", e)
                return False

    async def list_sessions(self) -> List[Dict[str, Any]]:
        """列出所有活跃会话。

        Returns:
            List[Dict]: 会话信息列表。
        """
        sessions_info = []
        for session_id, session in self._sessions.items():
            sessions_info.append({
                "session_id": session_id,
                "created_at": session.created_at,
                "last_used": session.last_used,
                "age_seconds": time.time() - session.created_at,
            })
        return sessions_info

    async def shutdown_session(self, session_id: str) -> bool:
        """关闭指定的会话。

        Args:
            session_id: 会话标识符。

        Returns:
            bool: 是否成功关闭。
        """
        async with self._lock:
            session = self._sessions.pop(session_id, None)
            if session:
                session.shutdown()
                logger.info("已关闭会话: %s", session_id)
                return True
            return False

    async def shutdown_all(self) -> None:
        """关闭所有会话。"""
        async with self._lock:
            for session in self._sessions.values():
                session.shutdown()
            self._sessions.clear()
            logger.info("已关闭所有内核会话")