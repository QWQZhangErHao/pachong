"""Priority scoring for crawl tasks.

MVP: Rule-based scoring based on URL patterns, domain value, and recency.
Future (Phase 9): LLM-based Craw4LLM-style scoring.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

# Pre-compiled URL patterns for priority classification
PRODUCT_PATTERNS = [
    r"/product(s)?/",
    r"/item(s)?/",
    r"/p/",
    r"/dp/",
    r"/gp/product/",
    r"/detail(s)?/",
    r"/goods/",
    r"/sku/",
    r"/shop/",
]

CATEGORY_PATTERNS = [
    r"/category(s)?/",
    r"/catalog/",
    r"/collection(s)?/",
    r"/department(s)?/",
    r"/shop/",
    r"/list/",
    r"/search/",
]

LOW_VALUE_PATTERNS = [
    r"/cart",
    r"/checkout",
    r"/login",
    r"/signup",
    r"/register",
    r"/account",
    r"/wishlist",
    r"/contact",
    r"/about",
    r"/help",
    r"/faq",
    r"/terms",
    r"/privacy",
    r"/shipping",
    r"/returns",
    r"/tracking",
    r"/order-status",
]

# Domain value multipliers (higher = more important)
DOMAIN_VALUE: dict[str, float] = {
    "amazon.com": 1.0,
    "walmart.com": 0.9,
    "target.com": 0.85,
    "ebay.com": 0.9,
    "etsy.com": 0.8,
    "aliexpress.com": 0.75,
    "shopify.com": 0.7,
}


def score_url(url: str, domain_value: float | None = None, recency_hours: float | None = None) -> int:
    """Score a URL from 0-100 based on pattern matching and domain value.

    Args:
        url: The URL to score.
        domain_value: Override for domain value (0.0-1.0).
        recency_hours: Hours since last crawl. More recent = slightly higher.

    Returns:
        Integer 0-100, where 100 is highest priority.
    """
    parsed = urlparse(url)
    path = parsed.path.lower()
    domain = parsed.hostname or ""

    # Base score from URL pattern
    score = 30.0  # default

    if _matches_any(path, PRODUCT_PATTERNS):
        score = 85.0
    elif _matches_any(path, CATEGORY_PATTERNS):
        score = 60.0
    elif _matches_any(path, LOW_VALUE_PATTERNS):
        score = 5.0

    # Domain value bonus (up to +10)
    if domain_value is not None:
        score += domain_value * 10
    else:
        for known_domain, val in DOMAIN_VALUE.items():
            if known_domain in domain:
                score += val * 10
                break

    # Recency boost: pages not crawled recently get priority (+0 to +5)
    if recency_hours is not None:
        score += min(5.0, recency_hours / 24.0)

    return min(100, max(0, int(score)))


def classify_url(url: str) -> str:
    """Classify a URL as 'product', 'category', 'low_value', or 'unknown'."""
    path = urlparse(url).path.lower()
    if _matches_any(path, PRODUCT_PATTERNS):
        return "product"
    if _matches_any(path, CATEGORY_PATTERNS):
        return "category"
    if _matches_any(path, LOW_VALUE_PATTERNS):
        return "low_value"
    return "unknown"


def _matches_any(path: str, patterns: list[str]) -> bool:
    # Normalize: ensure path has trailing / for consistent matching
    normalized = path if path.endswith("/") else path + "/"
    return any(re.search(p, normalized) for p in patterns)
