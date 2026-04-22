"""MCP 服务器连接池管理器。

管理多个 MCP 服务器的客户端连接，提供统一的获取接口。
"""

import asyncio
import logging
from typing import Dict, Optional

from janus_mcp.client import MCPClient, MCPClientConfig

logger = logging.getLogger(__name__)


class MCPManager:
    """MCP 服务器连接池管理器。

    使用示例:
        manager = MCPManager()
        sandbox_config = MCPClientConfig(server_url="http://localhost:8000")
        filesystem_config = MCPClientConfig(server_command="python", server_args=["-m", "mcp.servers.filesystem"])

        sandbox_client = await manager.get_client("sandbox", sandbox_config)
        fs_client = await manager.get_client("filesystem", filesystem_config)

        # 之后可通过名称复用已连接的客户端
        same_client = await manager.get_client("sandbox")  # 无需再传 config
    """

    def __init__(self) -> None:
        """初始化连接池管理器。"""
        self._clients: Dict[str, MCPClient] = {}
        self._configs: Dict[str, MCPClientConfig] = {}
        self._lock = asyncio.Lock()

    async def get_client(
        self,
        server_name: str,
        config: Optional[MCPClientConfig] = None,
    ) -> MCPClient:
        """获取或创建指定服务器的客户端连接。

        如果该服务器名称的客户端已存在且处于连接状态，则直接返回；
        否则使用提供的配置（或之前存储的配置）创建新客户端并连接。

        Args:
            server_name: 服务器唯一标识名称。
            config: 客户端配置。首次获取时必须提供，后续可省略。

        Returns:
            MCPClient: 已连接的客户端实例。

        Raises:
            ValueError: 首次获取时未提供 config 且无历史配置。
            MCPClientError: 连接失败。
        """
        async with self._lock:
            # 检查已有客户端
            if server_name in self._clients:
                client = self._clients[server_name]
                if client._connected:  # 简单检查，实际可增加心跳
                    logger.debug("复用已有客户端: %s", server_name)
                    return client
                else:
                    # 连接已断开，移除并重新创建
                    logger.warning("客户端 %s 已断开，重新创建", server_name)
                    del self._clients[server_name]

            # 确定使用的配置
            if config is not None:
                self._configs[server_name] = config
            else:
                config = self._configs.get(server_name)
                if config is None:
                    raise ValueError(f"首次获取客户端 '{server_name}' 必须提供 config")

            # 创建并连接客户端
            client = MCPClient(config)
            await client.connect()
            self._clients[server_name] = client
            logger.info("已创建并连接客户端: %s", server_name)
            return client

    async def close_client(self, server_name: str) -> None:
        """关闭并移除指定客户端。

        Args:
            server_name: 服务器名称。
        """
        async with self._lock:
            client = self._clients.pop(server_name, None)
            if client:
                await client.disconnect()
                logger.info("已关闭客户端: %s", server_name)

    async def close_all(self) -> None:
        """关闭所有客户端连接。"""
        async with self._lock:
            for name, client in list(self._clients.items()):
                await client.disconnect()
                logger.debug("已关闭客户端: %s", name)
            self._clients.clear()
            self._configs.clear()

    async def __aenter__(self) -> "MCPManager":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close_all()