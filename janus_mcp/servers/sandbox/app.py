"""MCP Sandbox 应用工厂。

创建并配置 FastMCP 实例，注册所有工具。
"""

import logging
from contextlib import asynccontextmanager

from fastmcp import FastMCP

from janus_mcp.servers.sandbox.config import ServerConfig
from janus_mcp.servers.sandbox.managers import (
    BrowserManager,
    JupyterKernelManager,
    KnowledgeManager,
    NoteManager,
)
from janus_mcp.servers.sandbox.tools import (
    register_browser_tools,
    register_code_tools,
    register_knowledge_tools,
    register_note_tools,
)

logger = logging.getLogger(__name__)


def create_app(config: ServerConfig) -> FastMCP:
    """创建配置好的 FastMCP 应用。

    Args:
        config: 服务端配置。

    Returns:
        FastMCP: 应用实例。
    """
    mcp = FastMCP(config.name)

    # 初始化管理器
    kernel_manager = JupyterKernelManager(
        workspace_path=config.workspace_path,
        kernel_name=config.kernel_name,
        max_sessions=config.max_kernel_sessions,
        execution_timeout=config.execution_timeout,
    )
    browser_manager = BrowserManager(headless=config.headless_browser)
    note_manager = NoteManager(storage_path=config.note_path)
    knowledge_manager = KnowledgeManager(knowledge_base_path=config.knowledge_base_path)

    # 定义 lifespan 上下文管理器来处理启动和关闭
    @asynccontextmanager
    async def lifespan(app: FastMCP):
        """应用生命周期管理。"""
        logger.info("Sandbox 服务启动中...")
        # 可在此进行预热操作，例如预启动内核
        try:
            await kernel_manager.get_or_create_kernel()
            logger.info("内核预热完成")
        except Exception as e:
            logger.warning("内核预热失败: %s", e)

        yield  # 应用运行期间

        # 关闭清理
        logger.info("Sandbox 服务关闭中，释放资源...")
        await kernel_manager.shutdown_all()
        await browser_manager.close()
        logger.info("资源释放完成")

    # 创建 FastMCP 实例，传入 lifespan
    mcp = FastMCP(config.name, lifespan=lifespan)

    # 注册工具（将管理器注入）
    register_code_tools(mcp, kernel_manager)
    register_browser_tools(mcp, browser_manager)
    register_note_tools(mcp, note_manager)
    register_knowledge_tools(mcp, knowledge_manager)

    @mcp.tool()
    async def health_check() -> dict:
        """健康检查。"""
        return {"status": "healthy", "service": config.name}

    logger.info("MCP Sandbox 应用已创建")
    return mcp