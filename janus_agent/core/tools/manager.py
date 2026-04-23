"""工具管理器。

负责统一管理本地工具与 MCP 远程工具，对外提供：
- 工具注册与初始化（拉取 MCP 工具列表）
- 生成 LLM 可用的 OpenAI 工具描述
- 统一调用入口（优先 MCP，本地回退）
- 智能参数适配
"""

import asyncio
import json
import logging
from typing import Any, Callable, Dict, List, Tuple

from janus_mcp.client import MCPClientConfig
from janus_mcp.dispatcher import MCPToolDispatcher
from janus_mcp.manager import MCPManager

from janus_agent.core.exceptions import ToolError
from janus_agent.core.tools.converters import (
    adapt_tool_arguments,
    mcp_tools_list_to_openai,
)

# 本地工具导入（仅在 MCP 不可用时回退）
from tools.note import NoteTool
from tools.executor import CodeExecutor
from tools.browser import BrowserTool
from tools.terminal import TerminalTool

logger = logging.getLogger(__name__)


class ToolManager:
    """统一工具管理器。

    职责：
    - 管理 MCP 远程工具（主用）和本地工具（备用）。
    - 生成 OpenAI 格式的工具列表供 LLM 使用。
    - 执行工具调用，智能适配参数，优先走 MCP，失败时回退到本地。

    Attributes:
        _local_functions: 本地异步函数映射 {tool_name: async_callable}。
        _mcp_dispatcher: MCP 工具分发器，用于远程调用。
        _mcp_initialized: 标记 MCP 工具是否已拉取。
        _openai_tools: 缓存的 OpenAI 工具描述列表（来自 MCP）。
    """

    def __init__(
        self,
        mcp_manager: MCPManager,
        mcp_dispatcher: MCPToolDispatcher,
        mcp_configs: List[Tuple[str, MCPClientConfig]],
    ) -> None:
        """初始化工具管理器。

        Args:
            mcp_manager: MCP 连接池管理器。
            mcp_dispatcher: MCP 工具分发器。
            mcp_configs: 列表，每个元素为 (server_name, MCPClientConfig)。
        """
        self._mcp_manager = mcp_manager
        self._mcp_dispatcher = mcp_dispatcher
        self._mcp_configs = mcp_configs
        self._mcp_initialized = False

        # 缓存 MCP 工具列表的 OpenAI 格式描述
        self._openai_tools: List[Dict[str, Any]] = []

        # 本地工具回退：仅当 MCP 调用失败时使用
        self._local_functions: Dict[str, Callable[..., Any]] = {}
        self._register_local_fallbacks()

    def _register_local_fallbacks(self) -> None:
        """注册本地工具异步函数，作为远程不可用时的回退方案。"""
        self._local_functions.update({
            "note_create": self._create_note_async,
            "note_search": self._search_notes_async,
            "execute_code": self._execute_code_async,
            "browser_navigate": self._browser_navigate_async,
            "terminal_run": self._run_shell_async,
            # 如需其他工具可在此补充
        })

    # ------------------------------------------------------------------
    # 公开接口：初始化与工具描述
    # ------------------------------------------------------------------

    async def initialize_mcp_tools(self) -> None:
        """连接所有 MCP 服务器，拉取工具列表并缓存为 OpenAI 格式。

        该方法幂等：多次调用不会重复注册。调用后才能使用 get_openai_tools() 和 mcp 优先调用。
        """
        if self._mcp_initialized:
            return

        for server_name, config in self._mcp_configs:
            try:
                # 注册服务器，拉取工具名称列表，建立映射
                logger.info("正在注册 MCP 服务器: %s (url=%s)", server_name, config.server_url)
                tools = await self._mcp_dispatcher.register_server(server_name, config)
                logger.info("MCP 服务器 %s 注册成功，提供工具: %s", server_name, tools)
            except Exception as e:
                logger.error("MCP 服务器 %s 注册失败: %s", server_name, e)
                raise ToolError(f"MCP 服务器 {server_name} 注册失败") from e

        # 通过第一个配置获取客户端，获取完整的工具元数据（含 inputSchema）
        if self._mcp_configs:
            # 获取客户端示例（任意一个，假设所有服务器工具已合并）
            dummy_name, dummy_config = self._mcp_configs[0]
            try:
                client = await self._mcp_manager.get_client(dummy_name, dummy_config)
                raw_tools = await client.list_tools()
                logger.info("MCP 原始工具列表长度: %d, 内容: %s", len(raw_tools), raw_tools)
                self._openai_tools = mcp_tools_list_to_openai(raw_tools)
            except Exception as e:
                logger.error("获取 MCP 工具列表失败: %s", e)
                raise ToolError("无法获取 MCP 工具列表") from e

        self._mcp_initialized = True
        logger.info("MCP 工具注册完成，共 %d 个工具", len(self._openai_tools))

    def get_openai_tools(self) -> List[Dict[str, Any]]:
        """获取当前可用的工具列表，以供 LLM 生成 function calling 请求。

        Returns:
            OpenAI 格式的工具描述列表。
        """
        if not self._mcp_initialized:
            logger.warning("MCP 工具尚未初始化，返回空列表。请先调用 initialize_mcp_tools()。")
            return []
        return self._openai_tools

    # ------------------------------------------------------------------
    # 核心调用逻辑
    # ------------------------------------------------------------------

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """统一工具调用入口。

        执行顺序：
        1. 参数适配（将 LLM 通用 'input' 转换为工具参数名）
        2. 如果 MCP 已就绪且工具在注册表中，优先通过 MCP 调用。
        3. MCP 调用失败或工具未注册于 MCP 时，回退到本地工具。
        4. 仍失败则抛出 ToolError。

        Args:
            tool_name: 工具名称。
            arguments: 工具参数字典（可能包含需适配的字段）。

        Returns:
            工具执行结果，已规范化为字符串。

        Raises:
            ToolError: 工具未注册或执行失败。
        """
        # 参数适配
        adapted_args = adapt_tool_arguments(tool_name, arguments)

        # 优先 MCP 调用
        if self._mcp_initialized and tool_name in self._mcp_dispatcher._tool_registry:
            try:
                result = await self._mcp_dispatcher.call_tool(tool_name, adapted_args)
                logger.info("MCP 工具 %s 调用成功", tool_name)
                return self._format_result(result)
            except Exception as e:
                logger.warning("MCP 工具 %s 调用失败，回退到本地: %s", tool_name, e)
        else:
            logger.debug("工具 %s 未在 MCP 注册，尝试本地回退", tool_name)

        # 本地回退
        local_func = self._local_functions.get(tool_name)
        if local_func:
            try:
                result = await local_func(**adapted_args)
                logger.info("本地工具 %s 调用成功", tool_name)
                return self._format_result(result)
            except Exception as e:
                raise ToolError(f"本地工具 {tool_name} 执行失败: {e}") from e

        # 完全未找到
        raise ToolError(f"工具 '{tool_name}' 未注册，且本地回退不存在")

    @staticmethod
    def _format_result(result: Any) -> str:
        """将工具返回值统一转换为字符串，便于 LLM 理解。"""
        if isinstance(result, str):
            return result
        if isinstance(result, (dict, list)):
            return json.dumps(result, ensure_ascii=False)
        return str(result)

    # ------------------------------------------------------------------
    # 本地工具异步封装（纯备用）
    # ------------------------------------------------------------------

    async def _create_note_async(self, title: str, content: str = "") -> str:
        """本地创建笔记。"""
        loop = asyncio.get_running_loop()
        tool = NoteTool()
        try:
            note = await loop.run_in_executor(None, tool.create, title, content)
            return f"笔记已创建，ID: {note.note_id}"
        except Exception as e:
            raise ToolError(f"本地笔记创建失败: {e}") from e

    async def _search_notes_async(self, query: str, limit: int = 5) -> str:
        """本地搜索笔记。"""
        loop = asyncio.get_running_loop()
        tool = NoteTool()
        results = await loop.run_in_executor(None, tool.search, query, limit)
        if not results:
            return "未找到匹配的笔记"
        formatted = "\n".join(
            [f"- [{r['note_id']}] {r['title']}: {r['preview'][:80]}" for r in results]
        )
        return formatted

    async def _execute_code_async(self, code: str) -> str:
        """本地代码执行。"""
        async with CodeExecutor() as executor:
            result = await executor.execute(code)
            if result["success"]:
                return "".join(result["stdout"])
            return "错误:\n" + "\n".join(result["stderr"])

    async def _browser_navigate_async(self, url: str) -> str:
        """本地浏览器导航。"""
        async with BrowserTool() as browser:
            nav = await browser.navigate(url)
            if not nav["success"]:
                return f"导航失败，状态码: {nav['status_code']}"
            content = await browser.get_content()
            return content.get("text", "")[:2000]

    async def _run_shell_async(self, command: str) -> str:
        """本地终端命令执行。"""
        loop = asyncio.get_running_loop()
        terminal = TerminalTool()
        try:
            result = await loop.run_in_executor(None, terminal.execute, command)
            if result["success"]:
                return result["output"]
            return f"命令失败: {result.get('output', '')}"
        finally:
            terminal.close_all()

    async def close(self) -> None:
        """释放资源（当前无需额外操作，MCP 连接由 MCPManager 统一管理）。"""
        pass