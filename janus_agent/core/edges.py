"""条件边逻辑。

定义 LangGraph 工作流中的路由决策函数。
"""

from typing import Literal

from langchain_core.messages import AIMessage

from janus_agent.core.state import AgentState


def should_continue(state: AgentState) -> Literal["tools", "__end__"]:
    """决定从 agent_node 之后的路由。

    依据最后一条 AIMessage 是否包含 tool_calls，以及当前迭代是否未超限。

    Args:
        state: 当前 Agent 状态。
        max_iterations: 配置的最大迭代次数。

    Returns:
        "tools": 需要继续调用工具。
        "__end__": 直接结束工作流。
    """
    # 如果已设置了 final_output，直接结束
    final_output = state.get("final_output", "")
    if final_output:
        return "__end__"

    # 检查最后一条消息
    messages = state.get("messages", [])
    if not messages:
        return "__end__"

    last_message = messages[-1]
    # 检查是否有待执行的工具调用
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        # 额外校验迭代次数
        iteration_count = state.get("iteration_count", 0)
        max_iterations = state.get("max_iterations", 10)
        if iteration_count < max_iterations:
            return "tools"

    # 否则结束
    return "__end__"