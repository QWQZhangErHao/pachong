"""Exception hierarchy for the entire system."""

from __future__ import annotations


class PachongError(Exception):
    """Base exception for all pachong errors."""


class ConfigurationError(PachongError):
    """Invalid or missing configuration."""


class NetworkError(PachongError):
    """Network-level failure (DNS, TCP, TLS, timeout)."""


class ProxyExhaustedError(NetworkError):
    """No healthy proxies available in the pool."""


class ProxyBannedError(NetworkError):
    """The current proxy has been banned by the target."""


class RateLimitError(PachongError):
    """Rate limit enforced — retry after backoff."""


class TokenExhaustedError(RateLimitError):
    """Redis token bucket exhausted for this domain."""


class AntiBotDetectedError(PachongError):
    """Target site returned an anti-bot challenge or block page."""


class ExtractionError(PachongError):
    """Data extraction failed for a page."""


class RuleExpiredError(ExtractionError):
    """Cached extraction rule no longer matches the page structure."""


class RenderError(PachongError):
    """JavaScript rendering (Splash/Playwright) failed."""


class StorageError(PachongError):
    """Database or object storage operation failed."""


class QueueError(PachongError):
    """Message queue operation failed."""


class CircuitBreakerOpenError(PachongError):
    """Circuit breaker is open — requests to this domain are paused."""


class LockAcquisitionError(PachongError):
    """Failed to acquire Redlock distributed lock."""
