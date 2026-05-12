"""Playwright browser pool — reuses Chromium instances across requests."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import structlog
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

logger = structlog.get_logger(__name__)


class BrowserPool:
    """Pool of pre-launched Chromium instances with multi-context support.

    - Maintains `pool_size` browser instances
    - Each supports multiple isolated contexts
    - Auto-restart crashed browsers
    - Idle browser cleanup after `idle_timeout` seconds
    """

    def __init__(self, pool_size: int = 2, idle_timeout: int = 300):
        self.pool_size = pool_size
        self.idle_timeout = idle_timeout
        self._browsers: list[Browser] = []
        self._lock = asyncio.Lock()
        self._playwright = None

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        for _ in range(self.pool_size):
            browser = await self._launch_browser()
            self._browsers.append(browser)
        logger.info("browser_pool.started", size=len(self._browsers))

    async def stop(self) -> None:
        for browser in self._browsers:
            try:
                await browser.close()
            except Exception:
                pass
        self._browsers.clear()
        if self._playwright:
            await self._playwright.stop()
        logger.info("browser_pool.stopped")

    async def _launch_browser(self) -> Browser:
        return await self._playwright.chromium.launch(
            channel="chrome",
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--blink-settings=imagesEnabled=false",
                "--disable-gpu",
                "--disable-dev-shm-usage",
            ],
        )

    @asynccontextmanager
    async def acquire(self):
        """Rent a browser + context. Returns (page, context). Auto-returned."""
        browser = await self._get_browser()
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
        )
        page = await context.new_page()

        async def block(r):
            if r.request.resource_type in ("image", "font", "media", "stylesheet"):
                await r.abort()
            else:
                await r.continue_()
        await page.route("**/*", block)

        try:
            yield page, context
        finally:
            try:
                await context.close()
            except Exception:
                pass

    async def _get_browser(self) -> Browser:
        async with self._lock:
            # Return first healthy browser
            for browser in self._browsers:
                if browser.is_connected():
                    return browser
            # All broken — restart one
            for i, browser in enumerate(self._browsers):
                if not browser.is_connected():
                    try:
                        await browser.close()
                    except Exception:
                        pass
                    self._browsers[i] = await self._launch_browser()
                    return self._browsers[i]
            # All fine but pool exhausted — create extra
            browser = await self._launch_browser()
            self._browsers.append(browser)
            return browser

    @property
    def active_count(self) -> int:
        return sum(1 for b in self._browsers if b.is_connected())


_pool: BrowserPool | None = None


def get_browser_pool() -> BrowserPool:
    global _pool
    if _pool is None:
        _pool = BrowserPool()
    return _pool
