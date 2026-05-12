"""Lightpanda subprocess manager — Zig-based headless browser.

Lightpanda is ~11x faster than Chrome with ~1/9 the memory footprint.
Communicates via Chrome DevTools Protocol (CDP) over WebSocket.
Auto-terminates after each session to prevent memory leaks.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import time

import structlog

from pachong.core.settings import NetworkSettings
from pachong.network.response import FetchResponse, TimingInfo

logger = structlog.get_logger(__name__)


class LightpandaEngine:
    """Manages Lightpanda subprocess lifecycle and CDP communication."""

    def __init__(self, settings: NetworkSettings) -> None:
        self.settings = settings
        self._binary: str = ""
        self._port: int = 9223

    async def _find_binary(self) -> str:
        """Locate the Lightpanda binary."""
        binary = self.settings.lightpanda_binary_path
        if shutil.which(binary):
            return binary

        # Try common locations
        candidates = [
            binary,
            "/usr/local/bin/lightpanda",
            "/opt/lightpanda/lightpanda",
            "lightpanda.exe",
        ]
        for c in candidates:
            if shutil.which(c):
                return c

        logger.warning("lightpanda.binary_not_found", fallback="lightpanda will be disabled")
        return ""

    async def start(self) -> None:
        """Verify binary availability."""
        self._binary = await self._find_binary()
        if self._binary:
            logger.info("lightpanda.ready", binary=self._binary)
        else:
            logger.warning("lightpanda.disabled")

    async def stop(self) -> None:
        pass  # Subprocesses are terminated after each request

    @property
    def is_available(self) -> bool:
        return bool(self._binary)

    async def fetch(
        self,
        url: str,
        timeout_ms: int = 30_000,
    ) -> FetchResponse:
        """Launch Lightpanda, navigate, and extract rendered HTML.

        Each request spawns a fresh Lightpanda process to prevent memory leaks
        from accumulating over long-running operations.
        """
        timing = TimingInfo(start_time=time.monotonic())

        if not self._binary:
            return FetchResponse(
                url=url,
                status_code=0,
                timing=timing,
                engine_used="lightpanda",
                error="Lightpanda binary not found",
            )

        process = None
        ws_url = ""

        try:
            # Launch Lightpanda with CDP port
            process = await asyncio.create_subprocess_exec(
                self._binary,
                f"--port={self._port}",
                "--headless",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Wait for CDP to become available (max 3 seconds)
            ws_url = await self._wait_for_cdp(timeout=3.0)

            if not ws_url:
                raise RuntimeError("Lightpanda CDP did not become available")

            # Connect via WebSocket and navigate
            content = await self._navigate_via_cdp(ws_url, url, timeout_ms)

            timing.total_ms = (time.monotonic() - timing.start_time) * 1000

            return FetchResponse(
                url=url,
                final_url=url,
                status_code=200,
                content=content,
                content_bytes=content.encode() if content else b"",
                timing=timing,
                engine_used="lightpanda",
            )

        except Exception as e:
            timing.total_ms = (time.monotonic() - timing.start_time) * 1000
            logger.warning("lightpanda.fetch_failed", url=url, error=str(e))
            return FetchResponse(
                url=url,
                status_code=0,
                timing=timing,
                engine_used="lightpanda",
                error=str(e),
            )
        finally:
            if process:
                try:
                    process.terminate()
                    await asyncio.wait_for(process.wait(), timeout=3)
                except (ProcessLookupError, asyncio.TimeoutError):
                    process.kill()
                    await process.wait()

    async def _wait_for_cdp(self, timeout: float = 3.0) -> str:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection("127.0.0.1", self._port),
                    timeout=1.0,
                )
                # Request CDP version to get WebSocket URL
                request = (
                    f"GET /json/version HTTP/1.1\r\n"
                    f"Host: 127.0.0.1:{self._port}\r\n"
                    f"Connection: close\r\n\r\n"
                )
                writer.write(request.encode())
                await writer.drain()

                data = await asyncio.wait_for(reader.read(8192), timeout=1.0)
                writer.close()

                body = data.decode().split("\r\n\r\n", 1)[-1]
                info = json.loads(body)
                return info.get("webSocketDebuggerUrl", "")
            except Exception:
                await asyncio.sleep(0.2)
        return ""

    async def _navigate_via_cdp(self, ws_url: str, url: str, timeout_ms: int) -> str:
        """Navigate using CDP WebSocket and return rendered HTML."""
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(ws_url) as ws:
                # Enable Page domain
                await ws.send_json({"id": 1, "method": "Page.enable"})

                # Navigate
                await ws.send_json({
                    "id": 2,
                    "method": "Page.navigate",
                    "params": {"url": url},
                })

                # Wait for load event
                content = ""
                deadline = time.monotonic() + timeout_ms / 1000
                while time.monotonic() < deadline:
                    msg = await asyncio.wait_for(ws.receive_json(), timeout=5.0)
                    if msg.get("method") == "Page.loadEventFired":
                        # Get document content
                        await ws.send_json({
                            "id": 3,
                            "method": "Runtime.evaluate",
                            "params": {"expression": "document.documentElement.outerHTML"},
                        })
                        result = await ws.receive_json()
                        content = result.get("result", {}).get("result", {}).get("value", "")
                        break

                return content
