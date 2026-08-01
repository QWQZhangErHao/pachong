"""JavaScript rendering via Splash or AWS Lambda.

Delegates JS rendering to an external service. Returns rendered HTML
that can be fed into CSS/XPath extractors.

Supports:
- Splash (open-source, Docker-deployable)
- AWS Lambda + Playwright (serverless rendering)
"""

from __future__ import annotations

import json
from urllib.parse import urljoin

import structlog
from aiohttp import ClientSession, ClientTimeout

from pachong.core.settings import ExtractorSettings

logger = structlog.get_logger(__name__)

SPLASH_EXECUTE_SCRIPT = """
function main(splash, args)
    splash:set_user_agent(args.ua)
    splash.images_enabled = false
    assert(splash:go(args.url))
    splash:wait(args.wait or 2)
    return {
        html = splash:html(),
        png = splash:png(),
        title = splash:title(),
        url = splash:url(),
    }
end
"""


class RenderService:
    """Delegates JS rendering to Splash or Lambda."""

    def __init__(self, settings: ExtractorSettings) -> None:
        self.settings = settings
        self.service_url = settings.render_service_url.rstrip("/")

    async def render(
        self,
        url: str,
        wait_seconds: float = 2.0,
        user_agent: str | None = None,
        timeout_ms: int | None = None,
    ) -> dict:
        """Render a page and return {html, png, title, url}.

        Args:
            url: URL to render
            wait_seconds: Time to wait after page load for JS to execute
            user_agent: Custom User-Agent
            timeout_ms: Request timeout

        Returns:
            dict with keys: html, png, title, url
        """
        if self.settings.render_service == "splash":
            return await self._render_splash(url, wait_seconds, user_agent, timeout_ms)
        elif self.settings.render_service == "lambda":
            return await self._render_lambda(url, wait_seconds, user_agent, timeout_ms)
        else:
            raise ValueError(f"Unknown render service: {self.settings.render_service}")

    async def _render_splash(
        self,
        url: str,
        wait_seconds: float,
        user_agent: str | None,
        timeout_ms: int | None,
    ) -> dict:
        """Render via Splash HTTP API."""
        timeout = ClientTimeout(total=(timeout_ms or self.settings.render_timeout_ms) / 1000)
        endpoint = urljoin(self.service_url, "/execute")

        params = {
            "lua_source": SPLASH_EXECUTE_SCRIPT,
            "url": url,
            "wait": wait_seconds,
            "ua": user_agent or "Mozilla/5.0 Chrome/130.0.0.0",
            "timeout": (timeout_ms or self.settings.render_timeout_ms) / 1000,
        }

        try:
            async with ClientSession(timeout=timeout) as session:
                async with session.post(endpoint, json=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return {
                            "html": data.get("html", ""),
                            "png": data.get("png", b""),
                            "title": data.get("title", ""),
                            "url": data.get("url", url),
                        }
                    else:
                        logger.warning("render.splash_error", status=resp.status, url=url)
                        return {"html": "", "png": b"", "title": "", "url": url}
        except Exception as e:
            logger.error("render.splash_failed", url=url, error=str(e))
            return {"html": "", "png": b"", "title": "", "url": url}

    async def _render_lambda(
        self,
        url: str,
        wait_seconds: float,
        user_agent: str | None,
        timeout_ms: int | None,
    ) -> dict:
        """Render via AWS Lambda (custom function with Playwright).

        The Lambda function must accept: {url, waitSeconds, userAgent}
        and return: {html, png (base64), title, finalUrl}
        """
        import base64

        timeout = ClientTimeout(total=(timeout_ms or self.settings.render_timeout_ms) / 1000)

        payload = {
            "url": url,
            "waitSeconds": wait_seconds,
            "userAgent": user_agent,
        }

        try:
            async with ClientSession(timeout=timeout) as session:
                async with session.post(self.service_url, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        body = json.loads(data.get("body", "{}"))
                        png_bytes = base64.b64decode(body.get("png", "")) if body.get("png") else b""
                        return {
                            "html": body.get("html", ""),
                            "png": png_bytes,
                            "title": body.get("title", ""),
                            "url": body.get("finalUrl", url),
                        }
                    else:
                        return {"html": "", "png": b"", "title": "", "url": url}
        except Exception as e:
            logger.error("render.lambda_failed", url=url, error=str(e))
            return {"html": "", "png": b"", "title": "", "url": url}

    async def render_for_extraction(
        self,
        url: str,
        user_agent: str | None = None,
    ) -> tuple[str, bytes | None]:
        """Convenience: render and return (html, screenshot_bytes)."""
        result = await self.render(url, user_agent=user_agent)
        png = result.get("png", b"")
        if isinstance(png, str):
            png = png.encode("latin-1") if png else b""
        return result.get("html", ""), png if isinstance(png, bytes) and len(png) > 0 else None
