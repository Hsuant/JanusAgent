"""MCP 会话管理。"""

import logging
from typing import Any, Dict, List, Optional

from janus_mcp.client.config import MCPClientConfig
from janus_mcp.client.exceptions import ToolExecutionError, ConnectionError
from janus_mcp.client.protocol import JSONRPCRequest, MCPMessageFactory
from janus_mcp.client.transport import HTTPTransport, MCPTransport, StdioTransport

logger = logging.getLogger(__name__)


class MCPSession:
    def __init__(self, config: MCPClientConfig):
        self.config = config
        self.transport = self._create_transport()
        self._initialized = False
        self._session_id: Optional[str] = None
        self._server_info: Dict = {}
        self._tools_cache: Optional[List] = None

    def _create_transport(self) -> MCPTransport:
        if self.config.transport == "http":
            return HTTPTransport(self.config)
        elif self.config.transport == "stdio":
            return StdioTransport(self.config)
        else:
            raise ValueError(f"不支持的传输类型: {self.config.transport}")

    async def initialize(self) -> None:
        if self._initialized:
            return
        req = MCPMessageFactory.create_initialize_request(
            self.config.client_name, self.config.client_version
        )
        resp = await self.transport.send_request(req)
        resp.raise_for_error()
        result = resp.result or {}
        self._server_info = result.get("serverInfo", {})
        self._session_id = result.get("sessionId")
        self._initialized = True
        logger.info("MCP 会话初始化成功: %s", self._server_info.get("name"))

    async def _ensure_initialized(self):
        if not self._initialized:
            await self.initialize()

    async def list_tools(self, force: bool = False) -> list | None:
        await self._ensure_initialized()
        if self._tools_cache is not None and not force:
            return self._tools_cache
        req = MCPMessageFactory.create_list_tools_request()
        resp = await self.transport.send_request(req)
        resp.raise_for_error()

        # 根据 MCP 规范，tools 在 result.tools 中
        tools = resp.result.get("tools", [])
        self._tools_cache = tools
        return self._tools_cache

    async def call_tool(self, tool_name: str, arguments: Optional[Dict] = None) -> Any:
        await self._ensure_initialized()
        req = MCPMessageFactory.create_call_tool_request(tool_name, arguments)
        resp = await self.transport.send_request(req)
        resp.raise_for_error()
        result = resp.result
        if result.get("isError"):
            raise ToolExecutionError(f"工具执行失败: {result.get('content')}")
        return result.get("content", [])

    async def close(self):
        await self.transport.close()
        self._initialized = False