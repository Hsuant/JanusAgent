"""核心异常定义。

集中管理 JanusAgent 运行时的各类异常，便于上层统一捕获和处理。
"""

from typing import Optional


class AgentError(Exception):
    """Agent 核心通用异常。

    所有自定义异常均继承自该类，便于捕获 Agent 层级的错误。

    Attributes:
        message: 错误描述。
        cause: 原始异常（可选），用于异常链。
    """

    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(message)
        self.cause = cause


class ConfigurationError(AgentError):
    """配置相关错误。

    通常在加载或解析配置文件、参数无效时抛出。
    """


class ToolError(AgentError):
    """工具调用相关错误。

    包括本地工具、MCP 工具的执行失败、超时、未注册等。
    """


class MaxIterationError(AgentError):
    """达到最大迭代次数仍未完成任务时抛出。"""