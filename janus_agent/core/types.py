"""核心自定义类型。

定义 Agent 运行过程中使用的数据类，增强代码可读性和类型安全。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from langchain_core.messages import BaseMessage


@dataclass
class ToolCall:
    """单次工具调用的信息。

    Attributes:
        tool_name: 工具名称。
        arguments: 工具参数。
        result: 工具返回结果（字符串形式）。
        error: 执行异常信息，成功时为 None。
    """

    tool_name: str
    arguments: Dict[str, Any]
    result: Optional[str] = None
    error: Optional[str] = None


@dataclass
class StepResult:
    """单个推理步骤的详细信息。

    Attributes:
        iteration: 当前迭代次数（从 0 开始）。
        llm_output: LLM 返回的 AIMessage（未经处理）。
        tool_calls: 该步骤触发的工具调用列表。
    """

    iteration: int
    llm_output: BaseMessage
    tool_calls: List[ToolCall] = field(default_factory=list)


@dataclass
class AgentResponse:
    """Agent 完整运行结果。

    Attributes:
        success: 是否成功完成任务（未超迭代或未被异常终止）。
        final_output: 最终的文本输出（最后一条 Assistant 消息的内容）。
        messages: 整个会话的消息历史。
        steps: 每步的详细记录（可选）。
        total_iterations: 实际消耗的迭代次数。
    """

    success: bool
    final_output: str
    messages: List[BaseMessage]
    steps: Optional[List[StepResult]] = None
    total_iterations: int = 0