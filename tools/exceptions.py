"""工具库自定义异常类。

定义工具库中可能抛出的各类异常，便于上层统一处理。
"""

from typing import Optional


class ToolsetError(Exception):
    """工具库基础异常类。

    所有自定义异常均继承自此基类。

    Attributes:
        message: 错误描述信息。
        tool_name: 发生错误的工具名称（可选）。
        cause: 原始异常对象（可选）。
    """

    def __init__(
        self,
        message: str,
        tool_name: Optional[str] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        """初始化异常。

        Args:
            message: 错误描述信息。
            tool_name: 工具名称。
            cause: 原始异常。
        """
        super().__init__(message)
        self.message = message
        self.tool_name = tool_name
        self.cause = cause

    def __str__(self) -> str:
        """返回格式化的错误字符串。"""
        if self.tool_name:
            return f"[{self.tool_name}] {self.message}"
        return self.message


class ConfigurationError(ToolsetError):
    """配置相关异常。"""
    pass


class BrowserError(ToolsetError):
    """浏览器操作异常。"""
    pass


class TerminalError(ToolsetError):
    """终端操作异常。"""
    pass


class NoteError(ToolsetError):
    """笔记操作异常。"""
    pass


class ExecutionError(ToolsetError):
    """代码执行异常。"""
    pass


class TimeoutError(ToolsetError):
    """操作超时异常。"""
    pass