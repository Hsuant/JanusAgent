"""MCP 客户端主入口。"""

import logging
from typing import Any, Dict, List, Optional

from janus_mcp.client.config import MCPClientConfig
from janus_mcp.client.exceptions import MCPClientError
from janus_mcp.client.session import MCPSession
from janus_mcp.client.tools import SandboxTools

logger = logging.getLogger(__name__)


class MCPClient:
    def __init__(self, config: Optional[MCPClientConfig] = None, **kwargs):
        if config is None:
            config = MCPClientConfig(**kwargs)
        self.config = config
        self._session = MCPSession(config)
        self._sandbox_tools: Optional[SandboxTools] = None
        self._connected = False

    @property
    def sandbox(self) -> SandboxTools:
        if self._sandbox_tools is None:
            self._sandbox_tools = SandboxTools(self._session)
        return self._sandbox_tools

    async def connect(self) -> None:
        try:
            await self._session.initialize()
            self._connected = True
        except Exception as e:
            raise MCPClientError(f"连接失败: {e}") from e

    async def disconnect(self) -> None:
        await self._session.close()
        self._connected = False

    async def list_tools(self) -> List[Any]:
        await self._ensure_connected()
        return await self._session.list_tools()

    async def call_tool(self, tool_name: str, arguments: Optional[Dict] = None) -> Any:
        await self._ensure_connected()
        content = await self._session.call_tool(tool_name, arguments)
        return SandboxTools._parse_result(content)

    # 便捷方法
    async def execute_code(self, code: str, **kwargs) -> Dict:
        await self._ensure_connected()
        return await self.sandbox.execute_code(code, **kwargs)

    async def browser_navigate(self, url: str, **kwargs) -> Dict:
        await self._ensure_connected()
        return await self.sandbox.browser_navigate(url, **kwargs)

    async def note_create(self, title: str, content: str, **kwargs) -> Dict:
        await self._ensure_connected()
        return await self.sandbox.note_create(title, content, **kwargs)

    async def knowledge_search_cve(self, query: str, **kwargs) -> Dict:
        await self._ensure_connected()
        return await self.sandbox.knowledge_search_cve(query, **kwargs)

    async def _ensure_connected(self):
        if not self._connected:
            await self.connect()

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()