"""JanusAgent 工具库。

提供本地可调用的网络安全工具集，包括：
- 浏览器自动化 (BrowserTool)
- 终端命令执行 (TerminalTool)
- 笔记管理 (NoteTool)
- 代码执行 (CodeExecutor)

所有工具均可直接实例化使用，或通过便捷函数调用。
"""

from tools.browser import BrowserTool, get_page_content, navigate
from tools.config import (
    BrowserConfig,
    ConfigLoader,
    ExecutorConfig,
    NoteConfig,
    TerminalConfig,
    ToolsetConfig,
    get_config,
    set_config,
)
from tools.exceptions import (
    BrowserError,
    ConfigurationError,
    ExecutionError,
    NoteError,
    TerminalError,
    TimeoutError,
    ToolsetError,
)
from tools.executor import CodeExecutor, execute_code, execute_code_sync
from tools.note import NoteTool, create_note, search_notes
from tools.terminal import TerminalTool, execute_command

__version__ = "0.1.0"

__all__ = [
    # 配置
    "ToolsetConfig",
    "BrowserConfig",
    "TerminalConfig",
    "NoteConfig",
    "ExecutorConfig",
    "ConfigLoader",
    "get_config",
    "set_config",
    # 异常
    "ToolsetError",
    "ConfigurationError",
    "BrowserError",
    "TerminalError",
    "NoteError",
    "ExecutionError",
    "TimeoutError",
    # 浏览器工具
    "BrowserTool",
    "navigate",
    "get_page_content",
    # 终端工具
    "TerminalTool",
    "execute_command",
    # 笔记工具
    "NoteTool",
    "create_note",
    "search_notes",
    # 代码执行器
    "CodeExecutor",
    "execute_code",
    "execute_code_sync",
]