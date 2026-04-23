"""构建并编译 Agent 的 StateGraph。

本模块负责创建 LangGraph 工作流，将定义的节点和边组织为可执行的 CompiledGraph。
"""
from typing import Any

from langgraph.graph import END, StateGraph

from janus_agent.core.edges import should_continue
from janus_agent.core.nodes import agent_node, tool_node
from janus_agent.core.state import AgentState
from janus_agent.core.tools.manager import ToolManager
from janus_agent.llm.loader import LLMChain


class AgentGraph:
    """Agent 状态图封装。

    负责构建和编译 LangGraph 工作流，并提供 invoke 方法。

    Attributes:
        graph: 编译后的状态图，可执行 ainvoke/astream。
    """

    def __init__(
        self,
        llm_chain: LLMChain,
        tool_manager: ToolManager,
        system_prompt: str,
        max_iterations: int = 10,
    ) -> None:
        """初始化并编译状态图。

        Args:
            llm_chain: LLM 调用链。
            tool_manager: 工具管理器。
            system_prompt: 系统提示词。
            max_iterations: 最大推理迭代次数。
        """
        self.llm_chain = llm_chain
        self.tool_manager = tool_manager
        self.system_prompt = system_prompt
        self.max_iterations = max_iterations
        self.graph = self._build_graph()

    def _build_graph(self):
        """构建 LangGraph 状态图。

        图结构:
            agent -> (should_continue)
                -> tools -> agent
                -> __end__

        Returns:
            编译后的 CompiledStateGraph。
        """
        workflow = StateGraph(AgentState)

        # 添加节点，使用闭包注入外部依赖
        async def _agent(state: AgentState):
            return await agent_node(
                state,
                self.llm_chain,
                self.tool_manager,
                self.system_prompt,
            )

        async def _tools(state: AgentState):
            return await tool_node(state, self.tool_manager)

        workflow.add_node("agent", _agent)
        workflow.add_node("tools", _tools)

        # 入口点
        workflow.set_entry_point("agent")

        # 条件边
        workflow.add_conditional_edges(
            "agent",
            should_continue,
            {
                "tools": "tools",
                "__end__": END,
            },
        )

        # 工具执行后返回 agent 继续推理
        workflow.add_edge("tools", "agent")

        return workflow.compile()

    async def invoke(self, initial_state: AgentState) -> dict[str, Any] | Any:
        """执行状态图，运行完整的 Agent 流程。

        Args:
            initial_state: 初始状态字典。

        Returns:
            最终状态字典。
        """
        return await self.graph.ainvoke(initial_state)
