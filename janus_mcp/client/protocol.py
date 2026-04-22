"""MCP 协议消息定义。"""

import json
import uuid
from typing import Any, Dict, Optional, Union

from pydantic import BaseModel, Field, ValidationError

from janus_mcp.client.exceptions import ProtocolError


class JSONRPCRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: Union[str, int] = Field(default_factory=lambda: str(uuid.uuid4()))
    method: str
    params: Optional[Dict[str, Any]] = None

    def to_json(self) -> str:
        return self.model_dump_json(exclude_none=True)


class JSONRPCResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: Union[str, int]
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None

    def raise_for_error(self):
        if self.error:
            raise ProtocolError(self.error.get("message", "Unknown error"), code=self.error.get("code"))


class MCPMessageFactory:
    @staticmethod
    def parse_response(data: Union[str, bytes, Dict]) -> JSONRPCResponse:
        """解析 JSON-RPC 响应。

        支持从字符串、字节或字典解析。
        """
        if isinstance(data, (str, bytes)):
            try:
                data = json.loads(data)
            except json.JSONDecodeError as e:
                raise ProtocolError(f"无效的 JSON 响应: {e}") from e
        try:
            return JSONRPCResponse.model_validate(data)
        except ValidationError as e:
            raise ProtocolError(f"响应格式不符合 JSON-RPC: {e}") from e

    @staticmethod
    def create_request(method: str, params: Optional[Dict] = None) -> JSONRPCRequest:
        return JSONRPCRequest(method=method, params=params)

    @staticmethod
    def create_initialize_request(client_name: str, client_version: str) -> JSONRPCRequest:
        params = {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": client_name, "version": client_version},
        }
        return JSONRPCRequest(method="initialize", params=params)

    @staticmethod
    def create_list_tools_request() -> JSONRPCRequest:
        return JSONRPCRequest(method="tools/list")

    @staticmethod
    def create_call_tool_request(tool_name: str, arguments: Optional[Dict] = None) -> JSONRPCRequest:
        params = {"name": tool_name, "arguments": arguments}
        return JSONRPCRequest(method="tools/call", params=params)