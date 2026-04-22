"""MCP 工具调用分发器。

负责将工具调用请求路由到正确的 MCP 服务器。
"""

import logging
from typing import Any, Dict, List, Optional

from janus_mcp.manager import MCPManager
from janus_mcp.client import MCPClientConfig

logger = logging.getLogger(__name__)


class MCPToolDispatcher:
    """MCP 工具调用分发器。

    维护工具名到服务器名的映射，支持自动路由和手动指定服务器。

    使用示例:
        manager = MCPManager()
        dispatcher = MCPToolDispatcher(manager)

        # 注册服务器（自动拉取工具列表并建立映射）
        await dispatcher.register_server("sandbox", MCPClientConfig(server_url="http://localhost:8000"))
        await dispatcher.register_server("filesystem", MCPClientConfig(server_command="python", ...))

        # 调用工具（自动路由）
        result = await dispatcher.call_tool("execute_code", {"code": "print('hello')"})
    """

    def __init__(self, manager: MCPManager) -> None:
        """初始化分发器。

        Args:
            manager: MCP 连接池管理器实例。
        """
        self._manager = manager
        self._tool_registry: Dict[str, str] = {}  # tool_name -> server_name
        self._server_tools: Dict[str, List[str]] = {}  # server_name -> [tool_names]

    async def register_server(
        self,
        server_name: str,
        config: MCPClientConfig,
        force_refresh: bool = False,
    ) -> List[str]:
        """注册 MCP 服务器并缓存其工具列表。

        会通过客户端连接获取服务器提供的所有工具，并建立工具名到服务器名的映射。

        Args:
            server_name: 服务器唯一名称。
            config: 客户端配置。
            force_refresh: 是否强制刷新已注册服务器的工具列表。

        Returns:
            List[str]: 该服务器提供的工具名称列表。

        Raises:
            MCPClientError: 连接或获取工具列表失败。
        """
        # 如果已注册且不强制刷新，直接返回缓存的工具列表
        if server_name in self._server_tools and not force_refresh:
            return self._server_tools[server_name]

        # 获取客户端（自动连接）
        client = await self._manager.get_client(server_name, config)

        # 获取工具列表
        tools = await client.list_tools()
        tool_names = [tool.get("name") for tool in tools if tool.get("name")]

        # 更新注册表
        # 先清除该服务器旧映射
        if server_name in self._server_tools:
            for old_tool in self._server_tools[server_name]:
                if self._tool_registry.get(old_tool) == server_name:
                    del self._tool_registry[old_tool]

        self._server_tools[server_name] = tool_names
        for tool_name in tool_names:
            self._tool_registry[tool_name] = server_name

        logger.info("已注册服务器 '%s'，提供 %d 个工具", server_name, len(tool_names))
        return tool_names

    async def call_tool(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        server_name: Optional[str] = None,
    ) -> Any:
        """调用 MCP 工具。

        如果指定了 server_name，则直接调用该服务器的工具；
        否则根据注册表自动查找工具所属的服务器。

        Args:
            tool_name: 工具名称。
            arguments: 工具参数。
            server_name: 可选，手动指定服务器名称。

        Returns:
            Any: 工具执行结果（已解析）。

        Raises:
            ValueError: 工具未注册或指定的服务器不存在。
            MCPClientError: 调用失败。
        """
        if server_name is None:
            server_name = self._tool_registry.get(tool_name)
            if server_name is None:
                raise ValueError(f"工具 '{tool_name}' 未注册，请先调用 register_server 或手动指定 server_name")

        # 获取客户端（已缓存连接）
        client = await self._manager.get_client(server_name)
        return await client.call_tool(tool_name, arguments)

    def list_available_tools(self) -> List[Dict[str, str]]:
        """列出所有已知工具及其所属服务器。

        Returns:
            List[Dict]: 每个元素包含 'name' 和 'server' 字段。
        """
        return [
            {"name": tool_name, "server": server_name}
            for tool_name, server_name in self._tool_registry.items()
        ]

    def get_server_tools(self, server_name: str) -> List[str]:
        """获取指定服务器提供的所有工具名称。

        Args:
            server_name: 服务器名称。

        Returns:
            List[str]: 工具名称列表，服务器未注册则返回空列表。
        """
        return self._server_tools.get(server_name, [])

    async def unregister_server(self, server_name: str) -> None:
        """取消注册服务器，并关闭其连接。

        Args:
            server_name: 服务器名称。
        """
        # 清除映射
        if server_name in self._server_tools:
            for tool_name in self._server_tools[server_name]:
                if self._tool_registry.get(tool_name) == server_name:
                    del self._tool_registry[tool_name]
            del self._server_tools[server_name]

        # 关闭连接
        await self._manager.close_client(server_name)
        logger.info("已注销服务器: %s", server_name)