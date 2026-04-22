"""MCP 客户端异常。"""

class MCPClientError(Exception):
    """客户端基础异常。"""
    def __init__(self, message: str, code: int = None, cause: Exception = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.cause = cause

class ConnectionError(MCPClientError):
    """连接错误。"""

class ProtocolError(MCPClientError):
    """协议错误。"""

class TimeoutError(MCPClientError):
    """超时错误。"""

class ToolExecutionError(MCPClientError):
    """工具执行错误。"""