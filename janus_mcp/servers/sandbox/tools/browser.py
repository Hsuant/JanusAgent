"""浏览器自动化 MCP 工具。"""

from typing import Any, Dict

from fastmcp import FastMCP

from janus_mcp.servers.sandbox.managers.browser_manager import BrowserManager


def register_browser_tools(mcp: FastMCP, browser_manager: BrowserManager) -> None:
    """注册浏览器工具。"""

    @mcp.tool()
    async def browser_navigate(url: str, wait_until: str = "load") -> Dict[str, Any]:
        """导航到指定 URL。"""
        return await browser_manager.navigate(url, wait_until)

    @mcp.tool()
    async def browser_get_content() -> Dict[str, Any]:
        """获取当前页面内容。"""
        return await browser_manager.get_content()

    @mcp.tool()
    async def browser_screenshot(full_page: bool = False) -> Dict[str, Any]:
        """截取页面。"""
        return await browser_manager.screenshot(full_page=full_page)

    @mcp.tool()
    async def browser_execute_script(script: str) -> Dict[str, Any]:
        """执行 JavaScript。"""
        return await browser_manager.execute_script(script)

    @mcp.tool()
    async def browser_click(selector: str) -> Dict[str, Any]:
        """点击元素。"""
        return await browser_manager.click(selector)

    @mcp.tool()
    async def browser_fill(selector: str, value: str) -> Dict[str, Any]:
        """填充表单。"""
        return await browser_manager.fill(selector, value)