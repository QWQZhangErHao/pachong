"""Learned sitemap — a directed graph of URL patterns discovered during crawling.

Used to prioritize high-value paths and avoid crawling dead ends.
Stored as a Redis-backed structure with PostgreSQL persistence for recovery.
"""

from __future__ import annotations

from pachong.storage.redis_.client import get_redis

SITEMAP_GRAPH_KEY = "sitemap:graph"
SITEMAP_PATTERNS_KEY = "sitemap:patterns:{domain}"
SITEMAP_VISITED_KEY = "sitemap:visited:{domain}"


async def record_page(domain: str, url_pattern: str, links_to: list[str]) -> None:
    """Record a page pattern and its outgoing link patterns for a domain."""
    redis = get_redis()
    pattern_key = SITEMAP_PATTERNS_KEY.format(domain=domain)

    # Store the pattern as a node
    await redis.sadd(pattern_key, url_pattern)

    # Store edges: url_pattern -> linked patterns
    if links_to:
        edge_key = f"{SITEMAP_GRAPH_KEY}:{domain}"
        for target in links_to:
            await redis.sadd(f"{edge_key}:{url_pattern}", target)

    # Mark as visited with timestamp
    import time
    visited_key = SITEMAP_VISITED_KEY.format(domain=domain)
    await redis.hset(visited_key, url_pattern, str(time.time()))


async def get_known_patterns(domain: str) -> set[str]:
    """Return all known URL patterns for a domain."""
    redis = get_redis()
    return await redis.smembers(SITEMAP_PATTERNS_KEY.format(domain=domain))


async def get_high_value_patterns(domain: str, min_links_in: int = 3) -> list[str]:
    """Return patterns that are linked from many other patterns (hub pages)."""
    redis = get_redis()
    patterns = await get_known_patterns(domain)
    scored: list[tuple[str, int]] = []

    for pattern in patterns:
        edge_key = f"{SITEMAP_GRAPH_KEY}:{domain}:{pattern}"
        incoming = await redis.scard(edge_key)
        if incoming >= min_links_in:
            scored.append((pattern, incoming))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [p for p, _ in scored]


async def get_unvisited_patterns(domain: str) -> set[str]:
    """Return patterns that are known but never visited."""
    redis = get_redis()
    all_patterns = await redis.smembers(SITEMAP_PATTERNS_KEY.format(domain=domain))
    visited = await redis.hkeys(SITEMAP_VISITED_KEY.format(domain=domain))
    return all_patterns - set(visited)


async def get_pattern_stats(domain: str) -> dict:
    """Return stats about the learned sitemap for a domain."""
    redis = get_redis()
    patterns = await redis.scard(SITEMAP_PATTERNS_KEY.format(domain=domain))
    visited = await redis.hlen(SITEMAP_VISITED_KEY.format(domain=domain))
    return {
        "total_patterns": patterns,
        "visited_patterns": visited,
        "unvisited_patterns": patterns - visited,
        "coverage_pct": round(visited / max(1, patterns) * 100, 1),
    }
