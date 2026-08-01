"""Extraction rule cache manager backed by Redis.

Rules are cached in Redis with TTL=24h for ultra-fast lookup.
PostgreSQL is the source of truth for persistence.
The hot path reads from Redis only — zero DB queries during extraction.
"""

from __future__ import annotations

import hashlib
import json

import structlog

from pachong.core.models import ExtractionRule
from pachong.storage.redis_.client import get_redis

logger = structlog.get_logger(__name__)

RULE_PREFIX = "extract:rule"
RULE_INDEX_KEY = "extract:rule_index:{domain}"
RULE_CACHE_TTL = 86_400  # 24 hours


def _pattern_hash(path_pattern: str) -> str:
    return hashlib.md5(path_pattern.encode()).hexdigest()[:12]


def _rule_key(domain: str, path_pattern: str) -> str:
    return f"{RULE_PREFIX}:{domain}:{_pattern_hash(path_pattern)}"


async def get_rules(domain: str, url: str) -> list[ExtractionRule]:
    """Get cached extraction rules for a domain+URL pattern.

    Tries exact path match first, then falls back to pattern matching.
    """
    redis = get_redis()
    from urllib.parse import urlparse

    path = urlparse(url).path

    # Get the rule index for this domain
    index_key = RULE_INDEX_KEY.format(domain=domain)
    pattern_keys = await redis.smembers(index_key)

    matched_rules: list[ExtractionRule] = []

    for pk in pattern_keys:
        # Check if this pattern matches the URL path
        pattern = pk.decode() if isinstance(pk, bytes) else pk
        if _path_matches(path, pattern):
            # Get the rules for this pattern
            rules_key = _rule_key(domain, pattern)
            rules_data = await redis.get(rules_key)
            if rules_data:
                rules_list = json.loads(rules_data)
                for r in rules_list:
                    matched_rules.append(ExtractionRule(**r))

    return matched_rules


async def cache_rules(domain: str, path_pattern: str, rules: list[ExtractionRule]) -> None:
    """Cache extraction rules in Redis. Also updates the domain index."""
    redis = get_redis()
    rules_key = _rule_key(domain, path_pattern)
    index_key = RULE_INDEX_KEY.format(domain=domain)

    rules_data = json.dumps([r.model_dump(mode="json") for r in rules])

    async with redis.pipeline() as pipe:
        pipe.set(rules_key, rules_data, ex=RULE_CACHE_TTL)
        pipe.sadd(index_key, path_pattern)
        pipe.expire(index_key, RULE_CACHE_TTL)
        await pipe.execute()

    logger.info("extract.rules_cached", domain=domain, pattern=path_pattern, rule_count=len(rules))


async def invalidate_rules(domain: str, path_pattern: str | None = None) -> None:
    """Remove cached rules for a domain (or specific pattern)."""
    redis = get_redis()
    if path_pattern:
        await redis.delete(_rule_key(domain, path_pattern))
    else:
        # Invalidate all rules for this domain
        index_key = RULE_INDEX_KEY.format(domain=domain)
        pattern_keys = await redis.smembers(index_key)
        keys_to_delete = [_rule_key(domain, pk.decode() if isinstance(pk, bytes) else pk) for pk in pattern_keys]
        keys_to_delete.append(index_key)
        if keys_to_delete:
            await redis.delete(*keys_to_delete)
        logger.info("extract.rules_invalidated", domain=domain)


async def has_rules(domain: str, url: str) -> bool:
    """Check if cached rules exist for this domain+URL."""
    redis = get_redis()
    from urllib.parse import urlparse

    path = urlparse(url).path
    index_key = RULE_INDEX_KEY.format(domain=domain)
    pattern_keys = await redis.smembers(index_key)

    for pk in pattern_keys:
        pattern = pk.decode() if isinstance(pk, bytes) else pk
        if _path_matches(path, pattern):
            return True
    return False


async def rule_stats(domain: str) -> dict:
    """Get rule cache statistics for a domain."""
    redis = get_redis()
    index_key = RULE_INDEX_KEY.format(domain=domain)
    pattern_count = await redis.scard(index_key)

    total_rules = 0
    pattern_keys = await redis.smembers(index_key)
    for pk in pattern_keys:
        pattern = pk.decode() if isinstance(pk, bytes) else pk
        data = await redis.get(_rule_key(domain, pattern))
        if data:
            total_rules += len(json.loads(data))

    return {"domain": domain, "patterns": pattern_count, "total_rules": total_rules}


def _path_matches(path: str, pattern: str) -> bool:
    """Simple path pattern matching.

    Supports: exact match, wildcard (*), and {param} placeholders.
    Examples:
        "/products/123" matches "/products/{id}"
        "/products/123" matches "/products/*"
    """
    import re

    # Convert pattern to regex
    pattern_re = re.escape(pattern)
    pattern_re = pattern_re.replace(r"\{id\}", r"[^/]+")
    pattern_re = pattern_re.replace(r"\{sku\}", r"[^/]+")
    pattern_re = pattern_re.replace(r"\{slug\}", r"[^/]+")
    pattern_re = pattern_re.replace(r"\{category\}", r"[^/]+")
    pattern_re = pattern_re.replace(r"\*", r"[^/]*")

    # Allow trailing content
    pattern_re = f"^{pattern_re}"

    return bool(re.match(pattern_re, path))
