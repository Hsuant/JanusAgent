"""客户端配置。"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class MCPClientConfig:
    server_url: Optional[str] = None          # HTTP 模式必需
    server_command: Optional[str] = None      # STDIO 模式必需
    server_args: List[str] = field(default_factory=list)
    server_env: Dict[str, str] = field(default_factory=dict)
    transport: str = "http"                   # "http" 或 "stdio"

    timeout: float = 120.0
    connect_timeout: float = 10.0
    max_retries: int = 3
    retry_delay: float = 1.0
    retry_backoff: float = 2.0

    headers: Dict[str, str] = field(default_factory=dict)
    verify_ssl: bool = True
    debug: bool = False

    client_name: str = "JanusAgent"
    client_version: str = "0.1.0"

    def __post_init__(self):
        if self.transport == "http" and not self.server_url:
            raise ValueError("HTTP 模式需要 server_url")
        if self.transport == "stdio" and not self.server_command:
            raise ValueError("STDIO 模式需要 server_command")