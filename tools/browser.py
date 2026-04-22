"""浏览器自动化工具。

基于 Playwright 提供浏览器操作能力，支持页面导航、内容提取、截图等。
"""

import asyncio
import base64
import logging
from typing import Any, Dict, List, Optional

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    Playwright,
)

from tools.config import BrowserConfig, get_config
from tools.exceptions import BrowserError
from tools.utils import retry

logger = logging.getLogger(__name__)


class BrowserTool:
    """浏览器自动化工具。

    封装 Playwright 的常用操作，提供简洁的 API。

    Attributes:
        config: 浏览器配置。
        _playwright: Playwright 实例。
        _browser: 浏览器实例。
        _context: 浏览器上下文。
        _page: 当前页面。
        _lock: 异步锁，保证线程安全。
    """

    def __init__(self, config: Optional[BrowserConfig] = None) -> None:
        """初始化浏览器工具。

        Args:
            config: 浏览器配置，如果为 None 则使用全局配置。
        """
        self.config = config or get_config().browser
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._lock = asyncio.Lock()
        self._initialized = False

        logger.debug("浏览器工具初始化，无头模式: %s", self.config.headless)

    async def _ensure_browser(self) -> None:
        """确保浏览器实例已启动。"""
        if not self._initialized:
            try:
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(
                    headless=self.config.headless,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                self._initialized = True
                logger.debug("Chromium 浏览器已启动")
            except Exception as e:
                raise BrowserError(f"启动浏览器失败: {e}", "browser") from e

    async def _ensure_context(self) -> BrowserContext | None:
        """确保浏览器上下文存在。

        Returns:
            BrowserContext: 浏览器上下文实例。
        """
        await self._ensure_browser()
        if self._context is None:
            context_options = {
                "viewport": {
                    "width": self.config.viewport_width,
                    "height": self.config.viewport_height,
                },
            }
            if self.config.user_agent:
                context_options["user_agent"] = self.config.user_agent
            self._context = await self._browser.new_context(**context_options)
            logger.debug("浏览器上下文已创建")
        return self._context

    async def get_page(self, new_page: bool = False) -> Page | None:
        """获取或创建页面。

        Args:
            new_page: 是否强制创建新页面。

        Returns:
            Page: Playwright 页面对象。
        """
        async with self._lock:
            context = await self._ensure_context()
            if new_page or self._page is None or self._page.is_closed():
                if self._page and not self._page.is_closed():
                    await self._page.close()
                self._page = await context.new_page()
                logger.debug("新页面已创建")
            return self._page

    @retry(max_attempts=2, delay=1.0, exceptions=(BrowserError,))
    async def navigate(
        self,
        url: str,
        wait_until: str = "domcontentloaded",
        timeout_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        """导航到指定 URL。

        Args:
            url: 目标 URL。
            wait_until: 等待条件，可选 "load"、"domcontentloaded"、"networkidle"。
            timeout_ms: 超时时间（毫秒），默认使用配置值。

        Returns:
            Dict: 导航结果，包含状态码、URL、标题等。

        Raises:
            BrowserError: 导航失败时抛出。
        """
        timeout_ms = timeout_ms or self.config.default_timeout
        page = await self.get_page()

        try:
            response = await page.goto(
                url,
                wait_until=wait_until,
                timeout=timeout_ms,
            )
            status_code = response.status if response else 0
            title = await page.title()
            current_url = page.url

            logger.info("导航到 %s，状态码: %s", current_url, status_code)
            return {
                "success": response is not None and response.ok,
                "status_code": status_code,
                "url": current_url,
                "title": title,
            }
        except Exception as e:
            raise BrowserError(f"导航到 {url} 失败: {e}", "navigate") from e

    async def get_content(self, include_html: bool = False) -> Dict[str, Any]:
        """获取当前页面内容。

        Args:
            include_html: 是否包含完整 HTML 源码。

        Returns:
            Dict: 包含页面标题、URL、文本内容和可选的 HTML 源码。

        Raises:
            BrowserError: 获取内容失败时抛出。
        """
        page = await self.get_page()

        try:
            title = await page.title()
            url = page.url
            text_content = await page.inner_text("body")

            result = {
                "success": True,
                "url": url,
                "title": title,
                "text": text_content,
            }

            if include_html:
                result["html"] = await page.content()

            return result
        except Exception as e:
            raise BrowserError(f"获取页面内容失败: {e}", "get_content") from e

    async def screenshot(
        self,
        full_page: bool = False,
        path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """截取当前页面。

        Args:
            full_page: 是否截取整个页面。
            path: 保存路径，如果为 None 则返回 base64 编码的图片数据。

        Returns:
            Dict: 包含截图结果，如果未指定路径则包含 "data" 字段（base64 编码）。

        Raises:
            BrowserError: 截图失败时抛出。
        """
        page = await self.get_page()

        try:
            if path:
                await page.screenshot(path=path, full_page=full_page)
                logger.info("截图已保存至: %s", path)
                return {
                    "success": True,
                    "path": path,
                    "full_page": full_page,
                }
            else:
                screenshot_bytes = await page.screenshot(full_page=full_page)
                data = base64.b64encode(screenshot_bytes).decode("utf-8")
                return {
                    "success": True,
                    "data": data,
                    "full_page": full_page,
                }
        except Exception as e:
            raise BrowserError(f"截图失败: {e}", "screenshot") from e

    async def click(
        self,
        selector: str,
        timeout_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        """点击页面元素。

        Args:
            selector: CSS 选择器或 XPath。
            timeout_ms: 超时时间（毫秒）。

        Returns:
            Dict: 点击结果。

        Raises:
            BrowserError: 点击失败时抛出。
        """
        timeout_ms = timeout_ms or self.config.default_timeout
        page = await self.get_page()

        try:
            await page.click(selector, timeout=timeout_ms)
            logger.debug("点击元素: %s", selector)
            return {"success": True, "selector": selector}
        except Exception as e:
            raise BrowserError(f"点击元素 {selector} 失败: {e}", "click") from e

    async def fill(
        self,
        selector: str,
        value: str,
        timeout_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        """填充表单字段。

        Args:
            selector: CSS 选择器。
            value: 填充的值。
            timeout_ms: 超时时间（毫秒）。

        Returns:
            Dict: 填充结果。

        Raises:
            BrowserError: 填充失败时抛出。
        """
        timeout_ms = timeout_ms or self.config.default_timeout
        page = await self.get_page()

        try:
            await page.fill(selector, value, timeout=timeout_ms)
            logger.debug("填充字段 %s: %s", selector, value)
            return {"success": True, "selector": selector, "value": value}
        except Exception as e:
            raise BrowserError(f"填充字段 {selector} 失败: {e}", "fill") from e

    async def execute_script(self, script: str) -> Dict[str, Any]:
        """在页面中执行 JavaScript 代码。

        Args:
            script: JavaScript 代码。

        Returns:
            Dict: 执行结果，包含返回值。

        Raises:
            BrowserError: 执行失败时抛出。
        """
        page = await self.get_page()

        try:
            result = await page.evaluate(script)
            logger.debug("执行脚本，返回值类型: %s", type(result).__name__)
            return {"success": True, "result": result}
        except Exception as e:
            raise BrowserError(f"执行脚本失败: {e}", "execute_script") from e

    async def wait_for_selector(
        self,
        selector: str,
        timeout_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        """等待元素出现。

        Args:
            selector: CSS 选择器。
            timeout_ms: 超时时间（毫秒）。

        Returns:
            Dict: 等待结果。

        Raises:
            BrowserError: 等待超时或失败时抛出。
        """
        timeout_ms = timeout_ms or self.config.default_timeout
        page = await self.get_page()

        try:
            await page.wait_for_selector(selector, timeout=timeout_ms)
            return {"success": True, "selector": selector}
        except Exception as e:
            raise BrowserError(f"等待元素 {selector} 超时: {e}", "wait_for_selector") from e

    async def get_elements_text(self, selector: str) -> List[str]:
        """获取所有匹配元素的文本内容。

        Args:
            selector: CSS 选择器。

        Returns:
            List[str]: 元素文本列表。

        Raises:
            BrowserError: 获取失败时抛出。
        """
        page = await self.get_page()

        try:
            elements = await page.query_selector_all(selector)
            texts = []
            for el in elements:
                text = await el.text_content()
                if text:
                    texts.append(text.strip())
            return texts
        except Exception as e:
            raise BrowserError(f"获取元素文本失败: {e}", "get_elements_text") from e

    async def close_page(self) -> None:
        """关闭当前页面。"""
        async with self._lock:
            if self._page and not self._page.is_closed():
                await self._page.close()
                self._page = None
                logger.debug("页面已关闭")

    async def close(self) -> None:
        """关闭浏览器并释放所有资源。"""
        async with self._lock:
            if self._page and not self._page.is_closed():
                await self._page.close()
                self._page = None
            if self._context:
                await self._context.close()
                self._context = None
            if self._browser:
                await self._browser.close()
                self._browser = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
            self._initialized = False
            logger.info("浏览器工具已关闭")

    async def __aenter__(self) -> "BrowserTool":
        """异步上下文管理器入口。"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器出口。"""
        await self.close()


# 便捷函数
async def navigate(url: str, **kwargs) -> Dict[str, Any]:
    """便捷函数：导航到指定 URL。"""
    async with BrowserTool() as browser:
        return await browser.navigate(url, **kwargs)


async def get_page_content(url: str) -> Dict[str, Any]:
    """便捷函数：获取指定 URL 的页面内容。"""
    async with BrowserTool() as browser:
        await browser.navigate(url)
        return await browser.get_content()