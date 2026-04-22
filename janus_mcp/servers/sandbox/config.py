"""MCP Sandbox 服务端配置。

定义服务运行时参数，支持从环境变量和配置文件加载。
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ServerConfig:
    """服务端配置类。

    Attributes:
        name: 服务名称。
        transport: 传输模式，'stdio' 或 'http'。
        host: HTTP 模式监听地址。
        port: HTTP 模式监听端口。
        workspace_path: 代码执行工作目录。
        note_path: 笔记存储目录。
        knowledge_base_path: 知识库目录。
        headless_browser: 浏览器是否无头模式。
        kernel_name: Jupyter 内核名称。
        max_kernel_sessions: 最大内核会话数。
        execution_timeout: 代码执行超时（秒）。
    """
    name: str = "AegisCracker Sandbox"
    transport: str = "stdio"  # 'stdio' 或 'http'
    host: str = "127.0.0.1"
    port: int = 8000

    workspace_path: str = field(default_factory=lambda: os.environ.get("WORKSPACE_PATH", "./workspace"))
    note_path: str = field(default_factory=lambda: os.environ.get("NOTE_PATH", "./notes"))
    knowledge_base_path: str = field(default_factory=lambda: os.environ.get("KNOWLEDGE_BASE_PATH", "./knowledge_base"))

    headless_browser: bool = True
    kernel_name: str = "python3"
    max_kernel_sessions: int = 5
    execution_timeout: int = 30

    def __post_init__(self) -> None:
        """确保目录存在。"""
        Path(self.workspace_path).mkdir(parents=True, exist_ok=True)
        Path(self.note_path).mkdir(parents=True, exist_ok=True)
        Path(self.knowledge_base_path).mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> "ServerConfig":
        """从环境变量构建配置。"""
        return cls(
            name=os.environ.get("MCP_SERVER_NAME", cls.name),
            transport=os.environ.get("MCP_TRANSPORT", cls.transport),
            host=os.environ.get("MCP_HOST", cls.host),
            port=int(os.environ.get("MCP_PORT", cls.port)),
            workspace_path=os.environ.get("WORKSPACE_PATH", cls.workspace_path),
            note_path=os.environ.get("NOTE_PATH", cls.note_path),
            knowledge_base_path=os.environ.get("KNOWLEDGE_BASE_PATH", cls.knowledge_base_path),
            headless_browser=os.environ.get("HEADLESS_BROWSER", "true").lower() == "true",
            kernel_name=os.environ.get("JUPYTER_KERNEL", cls.kernel_name),
        )