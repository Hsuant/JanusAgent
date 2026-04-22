"""STDIO 传输实现。"""

import asyncio
import json
import logging
import subprocess
import sys
from typing import Optional

from janus_mcp.client.config import MCPClientConfig
from janus_mcp.client.exceptions import ConnectionError, ProtocolError, TimeoutError
from janus_mcp.client.protocol import JSONRPCRequest, JSONRPCResponse, MCPMessageFactory
from janus_mcp.client.transport.base import MCPTransport

logger = logging.getLogger(__name__)


class StdioTransport(MCPTransport):
    """STDIO 传输，通过子进程标准输入输出通信。"""

    def __init__(self, config: MCPClientConfig):
        if not config.server_command:
            raise ValueError("STDIO 传输需要 server_command")
        self.config = config
        self._process: Optional[asyncio.subprocess.Process] = None
        self._lock = asyncio.Lock()
        self._debug = getattr(config, "debug", False)

    async def _ensure_process(self) -> asyncio.subprocess.Process:
        if self._process is None or self._process.returncode is not None:
            self._process = await asyncio.create_subprocess_exec(
                self.config.server_command,
                *self.config.server_args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={**self.config.server_env},
            )
            logger.info("启动 MCP 子进程 PID: %d", self._process.pid)
        return self._process

    async def send_request(self, request: JSONRPCRequest) -> JSONRPCResponse:
        async with self._lock:
            process = await self._ensure_process()
            if process.stdin is None or process.stdout is None:
                raise ConnectionError("子进程标准输入输出不可用")

            request_line = request.to_json() + "\n"

            # ========== 打印请求完整数据包 ==========
            if self._debug:
                logger.debug("STDIO 请求数据包:\n%s", request_line.strip())
            # ====================================

            process.stdin.write(request_line.encode())
            await process.stdin.drain()

            try:
                response_line = await asyncio.wait_for(
                    process.stdout.readline(),
                    timeout=self.config.timeout,
                )
            except asyncio.TimeoutError as e:
                raise TimeoutError(f"等待响应超时 ({self.config.timeout}秒)", cause=e)

            if not response_line:
                stderr = await process.stderr.read() if process.stderr else b""
                raise ConnectionError(f"子进程意外退出，stderr: {stderr.decode()}")

            response_str = response_line.decode().strip()

            # ========== 打印响应完整数据包 ==========
            if self._debug:
                logger.debug("STDIO 响应数据包:\n%s", response_str)
            # ====================================

            return MCPMessageFactory.parse_response(response_str)

    async def close(self) -> None:
        if self._process:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
            self._process = None