"""Response wrapper with timing breakdown, headers, and HAR-style metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class TimingInfo:
    """Granular request timing breakdown (milliseconds)."""
    dns_ms: float = 0.0
    tcp_ms: float = 0.0
    tls_ms: float = 0.0
    ttfb_ms: float = 0.0  # Time to first byte
    download_ms: float = 0.0
    total_ms: float = 0.0
    start_time: float = 0.0


@dataclass
class FetchResponse:
    """Unified response from any engine (HTTP, Playwright, Lightpanda, Nodriver)."""

    url: str
    status_code: int
    final_url: str = ""  # After redirects
    headers: dict[str, str] = field(default_factory=dict)
    content: str = ""  # HTML body
    content_bytes: bytes = b""
    timing: TimingInfo = field(default_factory=TimingInfo)
    engine_used: str = "http"
    proxy_used: str | None = None
    identity_id: str | None = None
    redirect_chain: list[str] = field(default_factory=list)
    cookies: dict[str, str] = field(default_factory=dict)
    har_entries: list[dict[str, Any]] = field(default_factory=list)
    screenshot_bytes: bytes | None = None
    screenshot_mime: str = "image/png"
    is_js_challenge: bool = False
    js_challenge_type: str = ""  # "cloudflare", "akamai", "datadome", "captcha"
    captured_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    error: str | None = None
    retry_count: int = 0

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    @property
    def is_blocked(self) -> bool:
        """Detect common anti-bot blocking patterns."""
        if self.status_code in (403, 429):
            return True
        if self.is_js_challenge:
            return True
        if self.status_code == 503 and self.js_challenge_type:
            return True
        return False

    @property
    def content_length(self) -> int:
        return len(self.content_bytes) or len(self.content.encode())

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "status_code": self.status_code,
            "final_url": self.final_url,
            "engine_used": self.engine_used,
            "proxy_used": self.proxy_used,
            "identity_id": self.identity_id,
            "timing": {
                "dns_ms": self.timing.dns_ms,
                "tcp_ms": self.timing.tcp_ms,
                "tls_ms": self.timing.tls_ms,
                "ttfb_ms": self.timing.ttfb_ms,
                "download_ms": self.timing.download_ms,
                "total_ms": self.timing.total_ms,
            },
            "is_blocked": self.is_blocked,
            "content_length": self.content_length,
            "redirect_chain": self.redirect_chain,
            "is_js_challenge": self.is_js_challenge,
            "js_challenge_type": self.js_challenge_type,
            "captured_at": self.captured_at,
            "error": self.error,
        }
