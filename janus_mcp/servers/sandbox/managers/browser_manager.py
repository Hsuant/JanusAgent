"""浏览器管理器。

基于 Playwright 提供浏览器自动化功能，支持页面操作、截图和内容提取。
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

try:
    from playwright.async_api import (
        async_playwright,
        Browser,
        BrowserContext,
        Page,
        Playwright,
    )
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    Browser = None  # type: ignore
    BrowserContext = None  # type: ignore
    Page = None  # type: ignore
    Playwright = None  # type: ignore

logger = logging.getLogger(__name__)


class BrowserManager:
    """浏览器管理器。

    管理 Playwright 浏览器实例，提供页面导航、内容提取、截图等功能。

    Attributes:
        headless: 是否使用无头模式。
        default_timeout: 默认超时时间（毫秒）。
        _playwright: Playwright 实例。
        _browser: 浏览器实例。
        _context: 浏览器上下文。
        _page: 当前页面。
    """

    def __init__(
        self,
        headless: bool = True,
        default_timeout: int = 30000,
    ) -> None:
        """初始化浏览器管理器。

        Args:
            headless: 是否使用无头模式。
            default_timeout: 默认超时时间（毫秒）。
        """
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError(
                "Playwright 未安装，请执行: pip install playwright && playwright install"
            )

        self.headless = headless
        self.default_timeout = default_timeout

        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._last_used = time.time()
        self._lock = asyncio.Lock()

        logger.info(
            "浏览器管理器初始化完成，无头模式: %s",
            "是" if headless else "否"
        )

    async def _ensure_browser(self) -> None:
        """确保浏览器实例已启动。"""
        if self._playwright is None:
            self._playwright = await async_playwright().start()
            logger.debug("Playwright 已启动")

        if self._browser is None:
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            logger.debug("Chromium 浏览器已启动")

    async def get_or_create_context(self) -> BrowserContext:
        """获取或创建浏览器上下文。

        Returns:
            BrowserContext: 浏览器上下文。
        """
        async with self._lock:
            await self._ensure_browser()

            if self._context is None:
                self._context = await self._browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                )
                logger.debug("浏览器上下文已创建")

            self._last_used = time.time()
            return self._context

    async def get_page(self) -> Page:
        """获取当前页面，如果不存在则创建。

        Returns:
            Page: Playwright 页面对象。
        """
        context = await self.get_or_create_context()

        if self._page is None or self._page.is_closed():
            self._page = await context.new_page()
            logger.debug("新页面已创建")

        self._last_used = time.time()
        return self._page

    async def navigate(self, url: str, wait_until: str = "load") -> Dict[str, Any]:
        """导航到指定 URL。

        Args:
            url: 目标 URL。
            wait_until: 等待条件，可选 "load"、"domcontentloaded"、"networkidle"。

        Returns:
            Dict: 导航结果，包含状态码、URL 和标题。
        """
        page = await self.get_page()

        try:
            response = await page.goto(
                url,
                wait_until=wait_until,
                timeout=self.default_timeout,
            )

            return {
                "success": response is not None and response.ok,
                "status_code": response.status if response else 0,
                "url": page.url,
                "title": await page.title(),
            }
        except Exception as e:
            logger.error("导航到 %s 失败: %s", url, e)
            return {
                "success": False,
                "status_code": 0,
                "url": url,
                "title": "",
                "error": str(e),
            }

    async def get_content(self) -> Dict[str, Any]:
        """获取当前页面内容。

        Returns:
            Dict: 包含 HTML 内容和文本内容的字典。
        """
        page = await self.get_page()

        try:
            html_content = await page.content()
            text_content = await page.inner_text("body")

            return {
                "success": True,
                "url": page.url,
                "title": await page.title(),
                "html": html_content,
                "text": text_content,
            }
        except Exception as e:
            logger.error("获取页面内容失败: %s", e)
            return {
                "success": False,
                "url": page.url if page else "",
                "error": str(e),
            }

    async def screenshot(
        self,
        full_page: bool = False,
        path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """截取当前页面。

        Args:
            full_page: 是否截取整个页面。
            path: 保存路径，如果为 None 则返回 base64 编码的图片。

        Returns:
            Dict: 包含截图结果和图片数据的字典。
        """
        page = await self.get_page()

        try:
            if path:
                await page.screenshot(path=path, full_page=full_page)
                return {
                    "success": True,
                    "path": path,
                    "full_page": full_page,
                }
            else:
                screenshot_bytes = await page.screenshot(full_page=full_page)
                import base64
                return {
                    "success": True,
                    "data": base64.b64encode(screenshot_bytes).decode("utf-8"),
                    "full_page": full_page,
                }
        except Exception as e:
            logger.error("截图失败: %s", e)
            return {
                "success": False,
                "error": str(e),
            }

    async def execute_script(self, script: str) -> Dict[str, Any]:
        """在页面中执行 JavaScript 代码。

        Args:
            script: 要执行的 JavaScript 代码。

        Returns:
            Dict: 执行结果。
        """
        page = await self.get_page()

        try:
            result = await page.evaluate(script)
            return {
                "success": True,
                "result": result,
            }
        except Exception as e:
            logger.error("执行脚本失败: %s", e)
            return {
                "success": False,
                "error": str(e),
            }

    async def click(self, selector: str) -> Dict[str, Any]:
        """点击页面元素。

        Args:
            selector: CSS 选择器。

        Returns:
            Dict: 点击结果。
        """
        page = await self.get_page()

        try:
            await page.click(selector, timeout=self.default_timeout)
            return {
                "success": True,
                "selector": selector,
            }
        except Exception as e:
            logger.error("点击元素 %s 失败: %s", selector, e)
            return {
                "success": False,
                "selector": selector,
                "error": str(e),
            }

    async def fill(self, selector: str, value: str) -> Dict[str, Any]:
        """填充表单字段。

        Args:
            selector: CSS 选择器。
            value: 填充的值。

        Returns:
            Dict: 填充结果。
        """
        page = await self.get_page()

        try:
            await page.fill(selector, value, timeout=self.default_timeout)
            return {
                "success": True,
                "selector": selector,
                "value": value,
            }
        except Exception as e:
            logger.error("填充字段 %s 失败: %s", selector, e)
            return {
                "success": False,
                "selector": selector,
                "error": str(e),
            }

    async def wait_for_selector(
        self,
        selector: str,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """等待元素出现。

        Args:
            selector: CSS 选择器。
            timeout: 超时时间（毫秒）。

        Returns:
            Dict: 等待结果。
        """
        page = await self.get_page()
        timeout = timeout or self.default_timeout

        try:
            await page.wait_for_selector(selector, timeout=timeout)
            return {
                "success": True,
                "selector": selector,
            }
        except Exception as e:
            logger.error("等待元素 %s 超时: %s", selector, e)
            return {
                "success": False,
                "selector": selector,
                "error": str(e),
            }

    async def close_page(self) -> None:
        """关闭当前页面。"""
        async with self._lock:
            if self._page and not self._page.is_closed():
                await self._page.close()
                self._page = None
                logger.debug("页面已关闭")

    async def close(self) -> None:
        """关闭所有浏览器资源。"""
        async with self._lock:
            if self._context:
                await self._context.close()
                self._context = None
            if self._browser:
                await self._browser.close()
                self._browser = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
            logger.info("浏览器管理器已关闭")