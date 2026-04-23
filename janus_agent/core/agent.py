"""JanusAgent 顶层入口。

整合配置、LLM、工具和图，提供异步任务执行和流式接口。
"""

import logging
from typing import Any, AsyncIterator, Dict, Optional

import uuid
from langchain_core.messages import HumanMessage

from janus_agent.core.graph import AgentGraph
from janus_agent.core.state import AgentState
from janus_agent.core.tools.manager import ToolManager
from janus_agent.core.types import AgentResponse
from janus_agent.llm.loader import LLMLoader
from janus_agent.llm.prompts import get_prompt_manager
from janus_mcp.client import MCPClientConfig
from janus_mcp.manager import MCPManager
from janus_mcp.dispatcher import MCPToolDispatcher
from config.loader import ConfigLoader

logger = logging.getLogger(__name__)


class JanusAgent:
    """基于 LangGraph 的多功能 Agent。

    负责初始化所有组件并提供 run/stream 接口。

    Example:
        agent = JanusAgent()
        await agent.initialize()
        response = await agent.run("扫描目标网站并记录结果")
    """

    def __init__(self, config_dir: str = "config") -> None:
        """初始化 Agent，但不执行耗时操作。

        Args:
            config_dir: 配置文件目录路径。
        """
        self._config_dir = config_dir
        self.llm_chain = None
        self.tool_manager = None
        self.graph = None
        self.system_prompt = ""
        self.max_iterations = 10
        self._initialized = False

        # MCP 组件
        self._mcp_manager = MCPManager()
        self._mcp_dispatcher = MCPToolDispatcher(self._mcp_manager)
        self._mcp_configs = []

        # 会话记忆存储：session_id -> 最后的状态（消息历史）
        self._sessions: Dict[str, AgentState] = {}

    async def initialize(self) -> None:
        """异步初始化所有资源。可重复调用，幂等。"""
        if self._initialized:
            return

        # 1. 加载配置
        config_loader = ConfigLoader(self._config_dir)
        agent_config = config_loader.load_agent_config()
        mcp_raw = config_loader.load_mcp_config()

        self.max_iterations = agent_config.get("max_iterations", 10)

        # 2. 初始化 LLMChain
        llm_loader = LLMLoader()
        llm_loader.load()  # 使用默认 config/llm.yaml
        self.llm_chain = llm_loader.create_llm_chain()

        # 3. 加载系统提示词
        pm = get_prompt_manager()
        try:
            self.system_prompt = pm.get_agent_system_prompt()
        except Exception:
            self.system_prompt = "你是一个智能助手，能够使用工具完成任务。"

        # 4. 构建 MCP 配置列表
        if not mcp_raw:
            logger.error("无法加载 mcp.yaml，请确保 config/mcp.yaml 存在且格式正确")
            raise RuntimeError("MCP 配置缺失")

        servers = mcp_raw.get("servers", [])
        if not servers:
            logger.error("mcp.yaml 中未定义任何服务器，请添加 sandbox 配置")
            raise RuntimeError("MCP 服务器列表为空")

        self._mcp_configs = []
        for srv in servers:
            if not srv.get("enabled", True):
                logger.info("跳过禁用的服务器: %s", srv.get("name"))
                continue
            cfg = srv.get("config", {})
            mcp_config = MCPClientConfig(
                transport=cfg.get("transport", "http"),
                server_url=cfg.get("server_url", "http://127.0.0.1:8000"),
                timeout=cfg.get("timeout", 120),
                connect_timeout=cfg.get("connect_timeout", 10),
                max_retries=cfg.get("max_retries", 3),
                retry_delay=cfg.get("retry_delay", 1.0),
                retry_backoff=cfg.get("retry_backoff", 2.0),
                headers=cfg.get("headers", {}),
                verify_ssl=cfg.get("verify_ssl", False),
            )
            self._mcp_configs.append((srv["name"], mcp_config))
            logger.info("MCP 服务器配置: %s -> %s", srv["name"], mcp_config.server_url)

        # 5. 创建工具管理器并初始化 MCP 工具列表
        self.tool_manager = ToolManager(
            self._mcp_manager,
            self._mcp_dispatcher,
            self._mcp_configs,
        )
        await self.tool_manager.initialize_mcp_tools()

        # 6. 编译图
        self.graph = AgentGraph(
            self.llm_chain,
            self.tool_manager,
            self.system_prompt,
            self.max_iterations,
        ).graph

        self._initialized = True
        logger.info("JanusAgent 初始化完成")

    @staticmethod
    def _build_mcp_config(srv: dict) -> MCPClientConfig:
        """辅助：从服务器字典构建 MCPClientConfig。"""
        cfg = srv.get("config", {})
        return MCPClientConfig(
            transport=cfg.get("transport", "http"),
            server_url=cfg.get("server_url", ""),
        )

    async def run(self, task: str, session_id: Optional[str] = None) -> AgentResponse:
        """执行任务，返回最终结果。

        Args:
            task: 用户自然语言任务。
            session_id: 可选会话 ID。如果提供且该会话已存在，则继续之前的对话；
                        否则创建新会话。不提供则每次创建新会话（无记忆）。

        Returns:
            AgentResponse 包含最终输出和元数据。
        """
        if not self._initialized:
            await self.initialize()

        if session_id is None:
            session_id = str(uuid.uuid4())

            # 从已有会话恢复状态
        if session_id in self._sessions:
            old_state = self._sessions[session_id]
            messages = old_state.get("messages", [])
            messages.append(HumanMessage(content=task))
            initial_state: AgentState = {
                "messages": messages,
                "task": task,
                "iteration_count": 0,
                "max_iterations": self.max_iterations,
                "final_output": "",
                "observation": "",
                "tool_results": [],
            }
        else:
            initial_state: AgentState = {
                "messages": [HumanMessage(content=task)],
                "task": task,
                "iteration_count": 0,
                "max_iterations": self.max_iterations,
                "final_output": "",
                "observation": "",
                "tool_results": [],
            }

        try:
            final_state = await self.graph.ainvoke(initial_state)
            messages = final_state.get("messages", [])
            final_answer = final_state.get("final_output", "")
            if not final_answer and messages:
                last_msg = messages[-1]
                final_answer = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

            # 保存会话状态，供后续调用
            self._sessions[session_id] = final_state

            return AgentResponse(
                success=True,
                final_output=final_answer,
                messages=messages,
                total_iterations=final_state.get("iteration_count", 0),
            )
        except Exception as e:
            logger.exception("Agent 运行异常: %s", e)
            return AgentResponse(
                success=False,
                final_output=f"运行错误: {e}",
                messages=initial_state.get("messages", []),
                total_iterations=0,
            )

    async def stream(self, task: str, session_id: Optional[str] = None) -> AsyncIterator[Dict[str, Any]]:
        """流式返回每一步的状态快照。支持会话记忆。"""
        if not self._initialized:
            await self.initialize()

        if session_id and session_id in self._sessions:
            messages = self._sessions[session_id].get("messages", [])
            messages.append(HumanMessage(content=task))
            initial_state: AgentState = {
                "messages": messages,
                "task": task,
                "iteration_count": 0,
                "max_iterations": self.max_iterations,
                "final_output": "",
                "observation": "",
                "tool_results": [],
            }
        else:
            initial_state: AgentState = {
                "messages": [HumanMessage(content=task)],
                "task": task,
                "iteration_count": 0,
                "max_iterations": self.max_iterations,
                "final_output": "",
                "observation": "",
                "tool_results": [],
            }

        async for event in self.graph.astream(initial_state):
            yield event

    async def close(self) -> None:
        """释放所有资源。"""
        if self._mcp_manager:
            await self._mcp_manager.close_all()
        self._initialized = False