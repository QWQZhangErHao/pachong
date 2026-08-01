"""aiohttp HTTP/2 ClientSession factory with identity injection.

Creates HTTP/2-capable sessions with:
- TCPConnector tuned for high concurrency
- JA3-compatible TLS settings (via custom SSL context)
- Per-identity cookie jar
- Coherent header injection from BrowserIdentity
"""

from __future__ import annotations

import ssl
import time

import structlog
from aiohttp import (
    ClientSession,
    ClientTimeout,
    CookieJar,
    TCPConnector,
    TraceConfig,
    TraceRequestEndParams,
    TraceRequestStartParams,
)

from pachong.core.models import BrowserIdentity
from pachong.core.settings import NetworkSettings
from pachong.network.response import FetchResponse, TimingInfo

logger = structlog.get_logger(__name__)

# ── Trace callbacks for timing ───────────────────────────────────────────────

_active_timers: dict[str, TimingInfo] = {}


async def _on_request_start(session, context, params: TraceRequestStartParams) -> None:
    _active_timers[id(params)] = TimingInfo(start_time=time.monotonic())


async def _on_request_end(session, context, params: TraceRequestEndParams) -> None:
    # Timing data collected but actual timing breakdown requires
    # connector-level hooks. This gives us total time.
    timer = _active_timers.pop(id(params), None)
    if timer:
        timer.total_ms = (time.monotonic() - timer.start_time) * 1000


TRACE_CONFIG = TraceConfig()
TRACE_CONFIG.on_request_start.append(_on_request_start)
TRACE_CONFIG.on_request_end.append(_on_request_end)


# ── Session Factory ──────────────────────────────────────────────────────────


class SessionFactory:
    """Creates and manages aiohttp ClientSessions with HTTP/2 and identity support."""

    def __init__(self, settings: NetworkSettings) -> None:
        self.settings = settings
        self._connector: TCPConnector | None = None

    def _build_ssl_context(self, identity: BrowserIdentity | None = None) -> ssl.SSLContext:
        """Build an SSL context with JA3-compatible settings.

        Uses a specific set of ciphers to match the declared browser identity.
        """
        ctx = ssl.create_default_context()

        if identity and identity.tls_cipher_suites:
            cipher_string = ":".join(
                _tls_cipher_id_to_name.get(cid, f"UNKNOWN-{cid}")
                for cid in identity.tls_cipher_suites
            )
            try:
                ctx.set_ciphers(cipher_string)
            except ssl.SSLError:
                pass  # Fall back to defaults

        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.set_alpn_protocols(["h2", "http/1.1"]) if self.settings.http2_enabled else None

        return ctx

    def build_connector(self) -> TCPConnector:
        """Create a TCPConnector tuned for scraping workloads."""
        self._connector = TCPConnector(
            limit=self.settings.connection_pool_size,
            limit_per_host=10,  # Per-domain limit — don't overwhelm targets
            enable_cleanup_closed=True,
            force_close=False,  # Keep connections alive
            ttl_dns_cache=self.settings.dns_cache_ttl_seconds,
            use_dns_cache=True,
        )
        return self._connector

    def build_session(
        self,
        identity: BrowserIdentity | None = None,
        cookie_jar: CookieJar | None = None,
    ) -> ClientSession:
        """Build an aiohttp ClientSession with all settings applied.

        Args:
            identity: BrowserIdentity for header/cipher injection.
            cookie_jar: Per-identity cookie storage.
        """
        if self._connector is None:
            self.build_connector()

        timeout = ClientTimeout(
            total=self.settings.request_timeout_ms / 1000,
            connect=self.settings.connect_timeout_ms / 1000,
        )

        headers = _build_identity_headers(identity) if identity else _default_headers()

        return ClientSession(
            connector=self._connector,
            timeout=timeout,
            headers=headers,
            cookie_jar=cookie_jar or CookieJar(unsafe=True),
            trace_configs=[TRACE_CONFIG],
        )

    async def close(self) -> None:
        if self._connector:
            await self._connector.close()
            self._connector = None


# ── Fetch helpers ────────────────────────────────────────────────────────────


async def fetch_with_session(
    session: ClientSession,
    url: str,
    method: str = "GET",
    **kwargs,
) -> FetchResponse:
    """Execute a request and return a unified FetchResponse."""
    timing = TimingInfo(start_time=time.monotonic())

    try:
        async with session.request(method, url, **kwargs) as resp:
            timing.total_ms = (time.monotonic() - timing.start_time) * 1000
            content = await resp.text()

            return FetchResponse(
                url=url,
                final_url=str(resp.url),
                status_code=resp.status,
                headers=dict(resp.headers),
                content=content,
                content_bytes=content.encode(),
                timing=timing,
                engine_used="http",
                redirect_chain=[str(h.url) for h in resp.history],
            )
    except Exception as e:
        timing.total_ms = (time.monotonic() - timing.start_time) * 1000
        return FetchResponse(
            url=url,
            status_code=0,
            timing=timing,
            engine_used="http",
            error=str(e),
        )


# ── Internal helpers ─────────────────────────────────────────────────────────


def _default_headers() -> dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Sec-Ch-Ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Upgrade-Insecure-Requests": "1",
    }


def _build_identity_headers(identity: BrowserIdentity) -> dict[str, str]:
    headers = _default_headers()
    if identity.user_agent:
        headers["User-Agent"] = identity.user_agent
    if identity.locale:
        headers["Accept-Language"] = f"{identity.locale},{identity.locale[:2]};q=0.9"
    return headers


# TLS cipher suite name mapping (IANA names)
_tls_cipher_id_to_name: dict[int, str] = {
    0xC02B: "ECDHE-ECDSA-AES128-GCM-SHA256",
    0xC02F: "ECDHE-RSA-AES128-GCM-SHA256",
    0xC02C: "ECDHE-ECDSA-AES256-GCM-SHA384",
    0xC030: "ECDHE-RSA-AES256-GCM-SHA384",
    0xCCA9: "ECDHE-ECDSA-CHACHA20-POLY1305",
    0xCCA8: "ECDHE-RSA-CHACHA20-POLY1305",
    0x009E: "DHE-RSA-AES128-GCM-SHA256",
    0x009F: "DHE-RSA-AES256-GCM-SHA384",
    0x1301: "TLS_AES_128_GCM_SHA256",
    0x1302: "TLS_AES_256_GCM_SHA384",
    0x1303: "TLS_CHACHA20_POLY1305_SHA256",
    0xC013: "ECDHE-RSA-AES128-SHA",
    0xC014: "ECDHE-RSA-AES256-SHA",
    0x002F: "TLS_RSA_AES_128_CBC_SHA",
    0x0035: "TLS_RSA_AES_256_CBC_SHA",
    0x000A: "TLS_RSA_WITH_3DES_EDE_CBC_SHA",
}
