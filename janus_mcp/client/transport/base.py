"""传输层抽象基类。"""

from abc import ABC, abstractmethod
from typing import Any, Dict

from janus_mcp.client.protocol import JSONRPCRequest, JSONRPCResponse


class MCPTransport(ABC):
    """MCP 传输层抽象基类。"""

    @abstractmethod
    async def send_request(self, request: JSONRPCRequest) -> JSONRPCResponse:
        """发送请求并返回响应。"""
        pass

    @abstractmethod
    async def close(self) -> None:
        """关闭传输。"""
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()