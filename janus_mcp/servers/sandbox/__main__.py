"""MCP Sandbox 服务入口。

可通过 `python -m mcp.server` 启动。
"""

import argparse
import logging

from janus_mcp.servers.sandbox.app import create_app
from janus_mcp.servers.sandbox.config import ServerConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="MCP Sandbox Server")
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio",
                        help="传输协议 (默认: stdio)")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP 监听地址")
    parser.add_argument("--port", type=int, default=8000, help="HTTP 监听端口")
    parser.add_argument("--workspace", default="./workspace", help="工作目录")
    parser.add_argument("--notes", default="./notes", help="笔记存储目录")
    parser.add_argument("--knowledge", default="./knowledge_base", help="知识库目录")
    parser.add_argument("--no-headless", action="store_true", help="禁用无头浏览器")
    args = parser.parse_args()

    config = ServerConfig(
        transport=args.transport,
        host=args.host,
        port=args.port,
        workspace_path=args.workspace,
        note_path=args.notes,
        knowledge_base_path=args.knowledge,
        headless_browser=not args.no_headless,
    )

    app = create_app(config)

    if config.transport == "http":
        logger.info("启动 HTTP 服务器，地址: http://%s:%d", config.host, config.port)
        app.run(transport="http", host=config.host, port=config.port)
    else:
        logger.info("启动 STDIO 服务器")
        app.run(transport="stdio")


if __name__ == "__main__":
    main()