"""Nodriver integration for resolving advanced JavaScript challenges.

Used only when JS challenges (Cloudflare, Akamai, DataDome) are detected.
Nodriver provides real-browser-based challenge solving, after which
cookies are extracted and reused by lighter engines for subsequent requests.

This is the most expensive engine — used sparingly as a last resort.
"""

from __future__ import annotations

import asyncio
import time

import structlog

from pachong.core.models import BrowserIdentity
from pachong.core.settings import NetworkSettings
from pachong.network.response import FetchResponse, TimingInfo

logger = structlog.get_logger(__name__)


class NodriverEngine:
    """Manages nodriver-based challenge resolution sessions.

    Launch a real browser via nodriver, solve the JS challenge,
    extract acquired cookies, and hand them off to lighter engines.
    """

    def __init__(self, settings: NetworkSettings) -> None:
        self.settings = settings
        self._semaphore = asyncio.Semaphore(settings.nodriver_max_concurrent)
        self._active_sessions = 0

    async def start(self) -> None:
        logger.info("nodriver.ready", max_concurrent=self.settings.nodriver_max_concurrent)

    async def stop(self) -> None:
        logger.info("nodriver.stopped")

    async def solve_and_fetch(
        self,
        url: str,
        identity: BrowserIdentity | None = None,
        timeout_ms: int = 60_000,
    ) -> FetchResponse:
        """Launch nodriver browser, navigate, wait for challenge resolution,
        extract the page content and acquired cookies.

        This is a heavy operation — limited by semaphore to prevent
        resource exhaustion.
        """
        timing = TimingInfo(start_time=time.monotonic())

        async with self._semaphore:
            self._active_sessions += 1
            try:
                result = await self._do_solve(url, identity, timeout_ms)
                timing.total_ms = (time.monotonic() - timing.start_time) * 1000
                result.timing = timing
                return result
            except Exception as e:
                timing.total_ms = (time.monotonic() - timing.start_time) * 1000
                logger.exception("nodriver.solve_failed", url=url)
                return FetchResponse(
                    url=url,
                    status_code=0,
                    timing=timing,
                    engine_used="nodriver",
                    error=str(e),
                )
            finally:
                self._active_sessions -= 1

    async def _do_solve(
        self,
        url: str,
        identity: BrowserIdentity | None,
        timeout_ms: int,
    ) -> FetchResponse:
        """Internal: execute nodriver-based challenge resolution."""
        try:
            import nodriver as nd
        except ImportError:
            return FetchResponse(
                url=url,
                status_code=0,
                timing=TimingInfo(),
                engine_used="nodriver",
                error="nodriver package not installed",
            )

        browser = None
        tab = None

        try:
            # Launch browser with realistic fingerprint
            browser_args = {
                "headless": False,  # Must be visible for challenge solving
            }

            browser = await nd.start(**browser_args)
            tab = await browser.get(url)

            # Wait for the page to load and any challenge to resolve
            await asyncio.sleep(3)

            # Wait for common challenge elements to disappear
            await self._wait_for_challenge_resolution(tab, timeout_ms)

            # Extract page content
            content = await tab.get_content()

            # Extract cookies for reuse by lighter engines
            cookies = await browser.cookies.get_all()
            cookie_dict: dict[str, str] = {}
            for c in cookies:
                if hasattr(c, "name"):
                    cookie_dict[c.name] = c.value if hasattr(c, "value") else str(c)

            return FetchResponse(
                url=url,
                final_url=str(tab.target.url) if hasattr(tab, "target") else url,
                status_code=200,
                content=content,
                content_bytes=content.encode() if isinstance(content, str) else content,
                engine_used="nodriver",
                cookies=cookie_dict,
                is_js_challenge=False,  # Assumed solved
            )

        finally:
            if tab:
                try:
                    await tab.close()
                except Exception:
                    pass
            if browser:
                try:
                    await browser.stop()
                except Exception:
                    pass

    async def _wait_for_challenge_resolution(self, tab, timeout_ms: int) -> None:
        """Poll until challenge indicators disappear or timeout."""
        deadline = time.monotonic() + timeout_ms / 1000

        while time.monotonic() < deadline:
            try:
                title = await tab.get_title() if hasattr(tab, "get_title") else ""
                content = await tab.get_content() if hasattr(tab, "get_content") else ""

                challenge_phrases = [
                    "just a moment",
                    "checking your browser",
                    "verifying you are human",
                    "ddos protection",
                    "please wait",
                    "security check",
                ]

                has_challenge = any(p in title.lower() or p in content.lower() for p in challenge_phrases)
                has_captcha = "captcha" in content.lower() or "recaptcha" in content.lower()

                if not has_challenge and not has_captcha:
                    return  # Challenge resolved

            except Exception:
                pass

            await asyncio.sleep(1)

    @property
    def active_sessions(self) -> int:
        return self._active_sessions
