"""终端操作工具。

基于 libtmux 提供 Tmux 会话管理，支持命令执行、会话复用和输出捕获。
"""

import asyncio
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

import platform
import subprocess
import libtmux
from libtmux import Server, Session

from tools.config import TerminalConfig, get_config
from tools.exceptions import TerminalError

logger = logging.getLogger(__name__)


class TerminalSession:
    """终端会话封装。

    封装单个 Tmux 会话，提供命令执行能力。

    Attributes:
        session_id: 会话唯一标识符。
        session_name: Tmux 会话名称。
        server: Tmux 服务器实例。
        session: Tmux 会话对象。
        window: 会话的窗口。
        pane: 主窗格。
    """

    def __init__(
        self,
        session_id: str,
        session_name: str,
        server: Server,
        session: Session,
    ) -> None:
        """初始化终端会话。

        Args:
            session_id: 会话标识符。
            session_name: Tmux 会话名称。
            server: Tmux 服务器实例。
            session: Tmux 会话对象。
        """
        self.session_id = session_id
        self.session_name = session_name
        self.server = server
        self.session = session
        self.window = session.attached_window
        self.pane = self.window.attached_pane
        self.created_at = time.time()
        self.last_used = time.time()

    def execute_command(
        self,
        command: str,
        timeout: int = 60,
        capture_lines: int = 500,
    ) -> Dict[str, Any]:
        """在终端中执行命令。

        Args:
            command: 要执行的命令。
            timeout: 超时时间（秒）。
            capture_lines: 最大捕获行数。

        Returns:
            Dict: 包含执行结果的字典。

        Raises:
            TerminalError: 执行失败时抛出。
            TimeoutError: 执行超时时抛出。
        """
        # 清空之前的输出
        self.pane.clear()

        # 发送命令
        self.pane.send_keys(command, enter=True)

        # 等待命令完成（通过检测提示符）
        start_time = time.time()
        output_lines: List[str] = []
        prompt_detected = False
        last_lines_count = 0
        stable_count = 0

        while time.time() - start_time < timeout:
            # 获取当前所有行
            current_lines = self.pane.capture_pane()
            if len(current_lines) > capture_lines:
                current_lines = current_lines[-capture_lines:]

            # 检测是否出现新的提示符（命令执行完成）
            if current_lines and current_lines[-1].strip().endswith(("$", "#", ">", "]", ")")):
                prompt_detected = True

            # 如果行数稳定且检测到提示符，认为命令执行完成
            if len(current_lines) == last_lines_count and prompt_detected:
                stable_count += 1
                if stable_count >= 3:  # 连续 3 次检查稳定
                    output_lines = current_lines
                    break
            else:
                stable_count = 0
                last_lines_count = len(current_lines)

            time.sleep(0.2)

        if not prompt_detected and time.time() - start_time >= timeout:
            raise TimeoutError(f"命令执行超时（{timeout} 秒）", "terminal")

        # 过滤掉命令本身和提示符行，保留实际输出
        filtered_output = self._filter_output(output_lines, command)
        self.last_used = time.time()

        return {
            "success": True,
            "command": command,
            "output": "\n".join(filtered_output),
            "lines": len(filtered_output),
            "session_id": self.session_id,
        }

    def _filter_output(self, lines: List[str], command: str) -> List[str]:
        """过滤输出行，移除命令回显和提示符。

        Args:
            lines: 原始输出行列表。
            command: 执行的命令。

        Returns:
            List[str]: 过滤后的输出行。
        """
        filtered = []
        skip_next = False
        command_found = False

        for line in lines:
            stripped = line.strip()
            # 跳过命令回显
            if not command_found and (command in stripped or stripped.endswith(command)):
                command_found = True
                continue
            # 跳过提示符行
            if stripped.endswith(("$", "#", ">", "]", ")")):
                continue
            # 跳过空行（连续多个空行压缩为一个）
            if not stripped:
                if filtered and filtered[-1] != "":
                    filtered.append("")
                continue
            filtered.append(line)

        # 移除尾部空行
        while filtered and filtered[-1] == "":
            filtered.pop()

        return filtered

    def close(self) -> None:
        """关闭会话。"""
        try:
            self.session.kill_session()
            logger.debug("终端会话 %s 已关闭", self.session_id)
        except Exception as e:
            logger.warning("关闭会话 %s 时出错: %s", self.session_id, e)


class TerminalTool:
    """终端操作工具。

    基于 Tmux 提供命令执行环境，支持会话复用。

    Attributes:
        config: 终端配置。
        _server: Tmux 服务器实例。
        _sessions: 活跃会话字典。
    """

    def __init__(self, config: Optional[TerminalConfig] = None) -> None:
        """初始化终端工具。

        Args:
            config: 终端配置，如果为 None 则使用全局配置。

        Raises:
            TerminalError: 无法连接 Tmux 服务器时抛出。
        """
        self.config = config or get_config().terminal
        self._is_windows = platform.system() == "Windows"

        if self._is_windows:
            self._sessions = None  # Windows 不使用 tmux
            logger.debug("Windows 环境，将使用 subprocess 执行命令")
        else:
            try:
                self._server = libtmux.Server()
                self._sessions: Dict[str, TerminalSession] = {}
                self._lock = asyncio.Lock()
                logger.debug("已连接到 Tmux 服务器")
            except Exception as e:
                raise TerminalError(f"无法连接 Tmux 服务器: {e}", "terminal") from e

        self._sessions: Dict[str, TerminalSession] = {}
        self._lock = asyncio.Lock()

    def _create_session(self, session_id: Optional[str] = None) -> TerminalSession:
        """创建新的 Tmux 会话。

        Args:
            session_id: 会话标识符，用于生成会话名称。

        Returns:
            TerminalSession: 新创建的会话对象。
        """
        session_id = session_id or f"term_{uuid.uuid4().hex[:8]}"
        session_name = f"{self.config.session_name_prefix}{session_id}"

        # 确保会话名称唯一
        existing = self._server.sessions.get(session_name=session_name, default=None)
        if existing:
            existing.kill_session()

        session = self._server.new_session(session_name=session_name, attach=False)
        terminal_session = TerminalSession(
            session_id=session_id,
            session_name=session_name,
            server=self._server,
            session=session,
        )
        self._sessions[session_id] = terminal_session
        logger.debug("已创建终端会话: %s", session_id)
        return terminal_session

    def get_session(self, session_id: Optional[str] = None) -> TerminalSession:
        """获取或创建终端会话。

        Args:
            session_id: 会话标识符，如果为 None 则创建新会话。

        Returns:
            TerminalSession: 终端会话对象。
        """
        if session_id and session_id in self._sessions:
            session = self._sessions[session_id]
            # 检查会话是否仍然有效
            try:
                _ = session.session.attached_window
                session.last_used = time.time()
                return session
            except Exception:
                # 会话已失效，重新创建
                del self._sessions[session_id]

        return self._create_session(session_id)

    def execute(
        self,
        command: str,
        session_id: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """执行终端命令。

        Args:
            command: 要执行的命令。
            session_id: 会话标识符，用于复用终端环境。
            timeout: 超时时间（秒），默认使用配置值。

        Returns:
            Dict: 包含执行结果的字典。

        Raises:
            TerminalError: 执行失败时抛出。
        """
        timeout = timeout or self.config.command_timeout
        if self._is_windows:
            # Windows 回退到 subprocess
            try:
                result = subprocess.run(
                    command, shell=True, capture_output=True, text=True, timeout=timeout
                )
                return {
                    "success": result.returncode == 0,
                    "command": command,
                    "output": result.stdout + result.stderr,
                    "lines": (result.stdout + result.stderr).count("\n"),
                    "session_id": None,
                }
            except subprocess.TimeoutExpired:
                raise TimeoutError(f"命令执行超时（{timeout} 秒）", "terminal")
            except Exception as e:
                raise TerminalError(f"执行命令失败: {e}", "execute", e)
        else:
            session = self.get_session(session_id)
            return session.execute_command(
                command,
                timeout=timeout,
                capture_lines=self.config.max_output_lines
            )

    async def execute_async(
        self,
        command: str,
        session_id: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """异步执行终端命令。

        Args:
            command: 要执行的命令。
            session_id: 会话标识符。
            timeout: 超时时间（秒）。

        Returns:
            Dict: 包含执行结果的字典。
        """
        if self._is_windows:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                self.execute,
                command,
                session_id,
                timeout
            )
        else:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                self.execute,
                command,
                session_id,
                timeout
            )

    def list_sessions(self) -> List[Dict[str, Any]]:
        """列出所有活跃的终端会话。

        Returns:
            List[Dict]: 会话信息列表。
        """
        sessions_info = []
        for sid, sess in self._sessions.items():
            try:
                _ = sess.session.attached_window
                status = "active"
            except Exception:
                status = "dead"
            sessions_info.append({
                "session_id": sid,
                "session_name": sess.session_name,
                "created_at": sess.created_at,
                "last_used": sess.last_used,
                "status": status,
            })
        return sessions_info

    def close_session(self, session_id: str) -> None:
        """关闭指定会话。

        Args:
            session_id: 会话标识符。

        Returns:
            bool: 是否成功关闭。
        """
        if self._is_windows:
            return
        for session in list(self._sessions.values()):
            session.close()
        self._sessions.clear()
        logger.info("所有终端会话已关闭")

    def close_all(self) -> None:
        """关闭所有会话。"""
        for session in list(self._sessions.values()):
            session.close()
        self._sessions.clear()
        logger.info("所有终端会话已关闭")

    def __enter__(self) -> "TerminalTool":
        """上下文管理器入口。"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """上下文管理器出口。"""
        self.close_all()


# 便捷函数
def execute_command(command: str, **kwargs) -> Dict[str, Any]:
    """便捷函数：执行终端命令。"""
    with TerminalTool() as term:
        return term.execute(command, **kwargs)