"""HTTP 传输实现。"""

import json
import asyncio
import logging
from typing import Optional

import httpx
from httpx import AsyncClient

from janus_mcp.client.config import MCPClientConfig
from janus_mcp.client.exceptions import ConnectionError, ProtocolError, TimeoutError
from janus_mcp.client.protocol import JSONRPCRequest, JSONRPCResponse, MCPMessageFactory
from janus_mcp.client.transport.base import MCPTransport

logger = logging.getLogger(__name__)


class HTTPTransport(MCPTransport):
    """HTTP + SSE 传输。

    符合 MCP 规范：POST /mcp 端点，Accept: text/event-stream，
    服务器通过 SSE 流返回响应事件。
    """

    def __init__(self, config: MCPClientConfig):
        """初始化 HTTP 传输。

        Args:
            config: 客户端配置，必须包含 server_url。

        Raises:
            ValueError: 如果 server_url 未设置。
        """
        if not config.server_url:
            raise ValueError("HTTP 传输需要 server_url")
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None
        self._base_url = config.server_url.rstrip("/")
        self._session_id: Optional[str] = None
        self._debug = getattr(config, "debug", False)

    async def _get_client(self) -> AsyncClient | None:
        """获取或创建 HTTP 客户端。"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=self.config.connect_timeout,
                    read=self.config.timeout,
                    write=self.config.timeout,
                    pool=self.config.connect_timeout,
                ),
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream", # 必须包含两种类型[reference:1],否则会报错
                    **self.config.headers
                },
                verify=self.config.verify_ssl,
            )
        return self._client

    async def send_request(self, request: JSONRPCRequest) -> JSONRPCResponse:
        """发送 JSON-RPC 请求并解析 SSE 响应。

        Args:
            equest: JSON-RPC 请求对象。

        Returns:
            JSONRPCResponse: 解析后的响应对象。

        Raises:
            ConnectionError: 网络或协议错误。
            TimeoutError: 请求超时。
        """
        client = await self._get_client()
        url = f"{self._base_url}/mcp"  # FastMCP 默认端点

        # 如果是非初始化请求且已有 Session ID，则添加到请求头
        headers = {}
        if request.method != "initialize" and self._session_id:
            headers["Mcp-Session-Id"] = self._session_id

        # ========== 打印请求完整数据包 ==========
        if self._debug:
            request_json = request.to_json()
            logger.debug("HTTP 请求数据包:\n%s", request_json)
        # ====================================

        for attempt in range(self.config.max_retries):
            try:
                async with client.stream(
                    method="POST",
                    url=url,
                    content=request.to_json(),
                    headers=headers,
                ) as response:
                    # 必须先调用 response.read() 或检查 status_code 再处理流
                    # 否则 httpx 会抛出 "Attempted to access streaming response content"
                    if response.status_code >= 400:
                        # 错误响应直接读取完整内容
                        error_body = await response.aread()
                        raise ConnectionError(
                            f"HTTP {response.status_code}: {error_body.decode()}",
                            code=response.status_code,
                        )

                    # 如果是 initialize 请求，从响应头捕获 Session ID
                    if request.method == "initialize":
                        session_id = response.headers.get("Mcp-Session-Id")
                        if session_id:
                            self._session_id = session_id
                            logger.debug("捕获 Session ID: %s", self._session_id)

                    return await self._parse_sse_stream(response)
            except httpx.TimeoutException as e:
                if attempt == self.config.max_retries - 1:
                    raise TimeoutError(f"请求超时 ({self.config.timeout}秒)", cause=e)
                await asyncio.sleep(
                    self.config.retry_delay * (self.config.retry_backoff ** attempt)
                )
            except httpx.HTTPStatusError as e:
                raise ConnectionError(
                    f"HTTP {e.response.status_code}: {e.response.text}",
                    code=e.response.status_code,
                    cause=e,
                ) from e
            except httpx.RequestError as e:
                raise ConnectionError(f"请求失败: {e}", cause=e) from e

        raise ConnectionError("超过最大重试次数")

    async def _parse_sse_stream(self, response: httpx.Response) -> JSONRPCResponse:
        """解析 SSE 流，提取 JSON-RPC 响应。

        根据 MCP 规范，服务器可能发送多个事件（如进度通知），
        我们只关心最终的 result 或 error 响应。

        Args:
            response: httpx 流式响应对象。

        Returns:
            JSONRPCResponse: 解析出的响应对象。

        Raises:
            ProtocolError: SSE 格式错误或响应无效。
        """
        current_event: Optional[str] = None
        data_buffer: str = ""
        last_response: Optional[JSONRPCResponse] = None

        async for line in response.aiter_lines():
            if not line:
                # 空行表示事件结束
                if current_event and data_buffer:
                    # 处理完整的事件
                    try:
                        # MCP 事件可能包含 "message" 类型
                        # 我们查找包含 result 或 error 的消息
                        if data_buffer.strip():
                            # 数据可能是一个 JSON 对象
                            data = json.loads(data_buffer)
                            if "result" in data or "error" in data:
                                resp = MCPMessageFactory.parse_response(data)
                                last_response = resp
                                # 如果这是最终响应，可以继续读取，但通常只有一个
                    except json.JSONDecodeError as e:
                        logger.warning("SSE 数据解析失败: %s", e)
                    current_event = None
                    data_buffer = ""
                continue

            if line.startswith("event:"):
                current_event = line[6:].strip()
            elif line.startswith("data:"):
                data_content = line[5:].strip()
                data_buffer += data_content
            else:
                # 可能是不规范的行，但作为数据追加
                data_buffer += line

        # 处理可能残留的数据
        if data_buffer and data_buffer.strip():
            try:
                data = json.loads(data_buffer)
                if "result" in data or "error" in data:
                    last_response = MCPMessageFactory.parse_response(data)
            except json.JSONDecodeError:
                pass

        if last_response is None:
            raise ProtocolError("未收到有效的 JSON-RPC 响应")

        # 检查错误
        last_response.raise_for_error()
        return last_response

    async def close(self) -> None:
        """关闭 HTTP 客户端。"""
        if self._client:
            await self._client.aclose()
            self._client = None