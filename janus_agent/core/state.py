"""Agent 状态定义。

基于 LangGraph 的 TypedDict，定义 Agent 运行时的完整共享状态。
"""

import operator
from typing import Annotated, Any, Dict, List, TypedDict

from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """Agent 状态字典。

    所有字段通过节点返回的字典进行部分更新，支持 reducer 自动合并。

    Attributes:
        messages: 对话历史，通过 add reducer 自动追加新消息。
        task: 用户最初的任务描述，贯穿整个执行过程。
        iteration_count: 已执行的迭代次数，每次进入决策节点时递增。
        max_iterations: 允许的最大迭代次数（从配置注入）。
        final_output: 非空字符串表示 LLM 已生成最终答案，可结束流程。
        observation: 最近一次工具执行后的观察文本，用于注入上下文。
        tool_results: 累积的工具调用结果记录（用于日志和反思）。
    """

    messages: Annotated[List[BaseMessage], operator.add]
    task: str
    iteration_count: int
    max_iterations: int
    final_output: str
    observation: str
    tool_results: List[Dict[str, Any]]