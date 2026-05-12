"""Playwright browser pool manager with request interception.

Maintains a pool of pre-launched Chromium instances. Intercepts and blocks
images, fonts, and analytics to reduce bandwidth by ~70%.
Injects fingerprint-override scripts before page load.
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager

import structlog

from pachong.core.models import BrowserIdentity
from pachong.core.settings import NetworkSettings
from pachong.network.response import FetchResponse, TimingInfo

logger = structlog.get_logger(__name__)


class PlaywrightEngine:
    """Browser pool using Playwright with request interception and fingerprint injection."""

    def __init__(self, settings: NetworkSettings) -> None:
        self.settings = settings
        self._pool: list[BrowserInstance] = []
        self._lock = asyncio.Lock()
        self._playwright = None
        self._browser_type = None

    async def start(self) -> None:
        """Launch the browser pool. Call once at startup."""
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._browser_type = self._playwright.chromium

        for _ in range(self.settings.playwright_browser_count):
            instance = await self._launch_browser()
            self._pool.append(instance)

        logger.info(
            "playwright.pool.started",
            browser_count=len(self._pool),
        )

    async def stop(self) -> None:
        """Close all browser instances and cleanup."""
        for instance in self._pool:
            await instance.close()
        self._pool.clear()
        if self._playwright:
            await self._playwright.stop()
        logger.info("playwright.pool.stopped")

    async def _launch_browser(self) -> "BrowserInstance":
        browser = await self._browser_type.launch(
            headless=self.settings.playwright_headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-infobars",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                "--disable-features=TranslateUI,BlinkGenPropertyTrees",
                "--disable-ipc-flooding-protection",
            ],
        )
        return BrowserInstance(browser, self.settings)

    async def acquire(self) -> "BrowserInstance":
        """Get an available browser instance from the pool. Blocks if none free."""
        while True:
            async with self._lock:
                for inst in self._pool:
                    if not inst.in_use:
                        inst.in_use = True
                        return inst

            logger.debug("playwright.pool.waiting")
            await asyncio.sleep(0.1)

    async def release(self, instance: "BrowserInstance") -> None:
        """Return a browser instance to the pool."""
        instance.in_use = False

        # Auto-restart if the browser crashed
        if not instance.is_alive:
            logger.warning("playwright.browser.restarting")
            async with self._lock:
                self._pool.remove(instance)
                new_inst = await self._launch_browser()
                self._pool.append(new_inst)


class BrowserInstance:
    """A single Chromium browser instance with its own context."""

    def __init__(self, browser, settings: NetworkSettings):
        self.browser = browser
        self.settings = settings
        self.in_use = False

    @property
    def is_alive(self) -> bool:
        return self.browser.is_connected() if self.browser else False

    async def close(self) -> None:
        try:
            await self.browser.close()
        except Exception:
            pass

    async def fetch(
        self,
        url: str,
        identity: BrowserIdentity | None = None,
        timeout_ms: int = 30_000,
    ) -> FetchResponse:
        """Navigate to a URL and return the rendered page content."""
        timing = TimingInfo(start_time=time.monotonic())
        context = None
        page = None

        try:
            context = await self.browser.new_context(
                viewport={"width": identity.screen_width if identity else 1920, "height": identity.screen_height if identity else 1080},
                user_agent=identity.user_agent if identity else None,
                locale=identity.locale if identity else "en-US",
                timezone_id=identity.timezone if identity else "America/New_York",
            )

            # ── Request interception: block heavy resources ──
            await context.route("**/*", self._route_handler)

            page = await context.new_page()

            # ── Inject fingerprint override ──
            if identity:
                await self._inject_fingerprint(page, identity)

            # ── Navigate ──
            response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

            status = response.status if response else 0
            content = await page.content()
            timing.total_ms = (time.monotonic() - timing.start_time) * 1000

            # ── Detect JS challenges ──
            challenge_type = await self._detect_challenge(page, status)

            return FetchResponse(
                url=url,
                final_url=page.url,
                status_code=status,
                content=content,
                content_bytes=content.encode(),
                timing=timing,
                engine_used="playwright",
                is_js_challenge=bool(challenge_type),
                js_challenge_type=challenge_type,
            )

        except Exception as e:
            timing.total_ms = (time.monotonic() - timing.start_time) * 1000
            return FetchResponse(
                url=url,
                status_code=0,
                timing=timing,
                engine_used="playwright",
                error=str(e),
            )
        finally:
            if page:
                await page.close()
            if context:
                await context.close()

    async def _route_handler(self, route) -> None:
        """Intercept requests — block images, fonts, and trackers."""
        if route.request.resource_type in ("image", "font", "media", "stylesheet"):
            if self.settings.playwright_block_images and route.request.resource_type == "image":
                await route.abort()
                return
            if self.settings.playwright_block_fonts and route.request.resource_type == "font":
                await route.abort()
                return
        await route.continue_()

    async def _inject_fingerprint(self, page, identity: BrowserIdentity) -> None:
        """Inject JS to override fingerprint-related properties before page load."""
        await page.add_init_script(f"""
            // Override navigator properties
            Object.defineProperty(navigator, 'hardwareConcurrency', {{ get: () => {identity.hardware_concurrency} }});
            Object.defineProperty(navigator, 'deviceMemory', {{ get: () => {identity.device_memory} }});
            Object.defineProperty(navigator, 'platform', {{ get: () => '{identity.platform}' }});
            Object.defineProperty(navigator, 'language', {{ get: () => '{identity.languages[0] if identity.languages else "en-US"}' }});
            Object.defineProperty(navigator, 'languages', {{ get: () => {identity.languages} }});

            // Override screen properties
            Object.defineProperty(screen, 'width', {{ get: () => {identity.screen_width} }});
            Object.defineProperty(screen, 'height', {{ get: () => {identity.screen_height} }});
            Object.defineProperty(screen, 'colorDepth', {{ get: () => {identity.color_depth} }});
            Object.defineProperty(screen, 'pixelDepth', {{ get: () => {identity.pixel_depth} }});

            // Override WebGL
            const getParameterProto = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(p) {{
                if (p === 37445) return '{identity.webgl_vendor}';
                if (p === 37446) return '{identity.webgl_renderer}';
                return getParameterProto.call(this, p);
            }};

            // Remove webdriver traces
            delete Object.getPrototypeOf(navigator).webdriver;
        """)

    async def _detect_challenge(self, page, status_code: int) -> str:
        """Detect anti-bot challenges on the page."""
        try:
            title = await page.title()

            # Cloudflare
            if "just a moment" in title.lower() or "__cf_chl_" in await page.content():
                return "cloudflare"

            # Akamai
            if status_code == 403 and "/_bm/" in await page.content():
                return "akamai"

            # DataDome
            cookies = await page.context.cookies()
            for c in cookies:
                if c["name"].startswith("datadome"):
                    return "datadome"

            # Generic CAPTCHA
            if "recaptcha" in await page.content().lower() or "hcaptcha" in await page.content().lower():
                return "captcha"

            # Blank page with only script
            body_text = await page.inner_text("body")
            if len(body_text.strip()) < 10 and "<script" in await page.content():
                return "suspicious_blank"

        except Exception:
            pass
        return ""
