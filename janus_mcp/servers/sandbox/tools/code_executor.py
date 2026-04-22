"""代码执行相关 MCP 工具。"""

from typing import Any, Dict, Optional

from fastmcp import FastMCP

from janus_mcp.servers.sandbox.managers.kernel_manager import JupyterKernelManager


def register_code_tools(mcp: FastMCP, kernel_manager: JupyterKernelManager) -> None:
    """注册代码执行工具。

    Args:
        mcp: FastMCP 应用实例。
        kernel_manager: Jupyter 内核管理器。
    """

    @mcp.tool()
    async def execute_code(
        code: str,
        session_id: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """在 Jupyter 内核中执行 Python 代码。

        Args:
            code: 要执行的 Python 代码。
            session_id: 会话标识符，用于保持执行上下文。
            timeout: 超时时间（秒）。

        Returns:
            Dict: 包含 stdout、stderr 和 session_id 的结果。
        """
        return await kernel_manager.execute_code(code, session_id, timeout)

    @mcp.tool()
    async def restart_kernel(session_id: str) -> Dict[str, Any]:
        """重启 Jupyter 内核，清除所有状态。

        Args:
            session_id: 会话标识符。

        Returns:
            Dict: 操作结果。
        """
        success = await kernel_manager.restart_kernel(session_id)
        return {"success": success, "session_id": session_id}

    @mcp.tool()
    async def list_kernel_sessions() -> Dict[str, Any]:
        """列出所有活跃的内核会话。

        Returns:
            Dict: 会话列表。
        """
        sessions = await kernel_manager.list_sessions()
        return {"sessions": sessions, "count": len(sessions)}