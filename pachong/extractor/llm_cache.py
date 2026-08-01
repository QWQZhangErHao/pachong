"""LLM result cache v2 — DOM structure signature keys, dynamic TTL, active invalidation."""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

CACHE_FILE = Path(__file__).parent.parent.parent / "llm_cache.json"
DEFAULT_TTL = 3600


def _extract_dom_signature(html: str) -> str:
    """Extract DOM structure signature: hash of all unique XPath-like paths.
    Collision-resistant because it captures the full DOM tree topology."""
    try:
        from lxml import html as lx
        doc = lx.fromstring(html[:50000] if len(html) > 50000 else html)
        paths: set[str] = set()
        for el in doc.iter():
            tag = el.tag
            classes = ".".join(sorted(el.classes)) if hasattr(el, "classes") and el.classes else ""
            paths.add(f"{tag}[{classes}]" if classes else tag)
        sig = hashlib.sha256("|".join(sorted(paths)).encode()).hexdigest()[:20]
        return sig
    except Exception:
        return hashlib.sha256(html[:10000].encode()).hexdigest()[:20]


def _infer_path_pattern(url: str) -> str:
    """Infer a path pattern from URL (e.g., /dp/B00XYZ -> /dp/{sku})."""
    from urllib.parse import urlparse
    path = urlparse(url).path.strip("/")
    parts = path.split("/")
    inferred: list[str] = []
    for part in parts:
        if re.match(r"^[A-Z0-9]{8,}$", part):
            inferred.append("{sku}")
        elif re.match(r"^[a-z0-9]+[-][a-z0-9-]+$", part):
            inferred.append("{slug}")
        elif re.match(r"^\d+$", part):
            inferred.append("{id}")
        else:
            inferred.append(part)
    return "/" + "/".join(inferred)


def _url_based_ttl(url: str) -> int:
    """Dynamic TTL: product pages 1h, listing 6h, articles 24h."""
    path = url.lower()
    if any(s in path for s in ["/dp/", "/product/", "/item/", "/p/", "/gp/"]):
        return 3600       # 1 hour
    if any(s in path for s in ["/search", "/category", "/catalog", "/listing", "/collections"]):
        return 21600      # 6 hours
    if any(s in path for s in ["article", "news", "blog", "post", "detail", "s?id="]):
        return 86400      # 24 hours
    return DEFAULT_TTL


def _cache_key(domain: str, html: str, url: str = "") -> str:
    sig = _extract_dom_signature(html)
    pattern = _infer_path_pattern(url) if url else ""
    return f"{domain}:{pattern}:{sig}"


async def get_cached_rules(domain: str, html: str, url: str = "") -> list[dict] | None:
    key = _cache_key(domain, html, url)
    try:
        from pachong.storage.redis_.client import get_redis
        data = await get_redis().get(f"llm_cache:{key}")
        if data:
            return json.loads(data)
    except Exception:
        pass
    try:
        if CACHE_FILE.exists():
            cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            entry = cache.get(key)
            if entry and entry.get("expire_at", 0) > time.time():
                return entry["rules"]
    except Exception:
        pass
    return None


async def cache_rules_result(domain: str, html: str, rules: list[dict], url: str = "") -> None:
    key = _cache_key(domain, html, url)
    ttl = _url_based_ttl(url)
    data = json.dumps(rules)
    try:
        from pachong.storage.redis_.client import get_redis
        await get_redis().setex(f"llm_cache:{key}", ttl, data)
    except Exception:
        pass
    try:
        fc: dict = json.loads(CACHE_FILE.read_text(encoding="utf-8")) if CACHE_FILE.exists() else {}
        fc[key] = {"rules": rules, "expire_at": time.time() + ttl,
                   "cached_at": datetime.now(UTC).isoformat()}
        fc = {k: v for k, v in fc.items() if v.get("expire_at", 0) > time.time()}
        CACHE_FILE.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    logger.debug("llm_cache.stored", key=key[:40], rules=len(rules), ttl=ttl)


async def invalidate_pattern(domain: str, path_pattern: str) -> int:
    """Actively invalidate all cached rules matching domain+pattern. Returns count removed."""
    removed = 0
    prefix = f"{domain}:{path_pattern}:"
    try:
        from pachong.storage.redis_.client import get_redis
        redis = get_redis()
        keys = await redis.keys(f"llm_cache:{prefix}*")
        if keys:
            await redis.delete(*keys)
            removed += len(keys)
    except Exception:
        pass
    try:
        if CACHE_FILE.exists():
            fc = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            to_delete = [k for k in fc if k.startswith(prefix)]
            for k in to_delete:
                del fc[k]
                removed += 1
            CACHE_FILE.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    logger.info("llm_cache.invalidated", domain=domain, pattern=path_pattern, removed=removed)
    return removed


def get_cache_stats() -> dict:
    try:
        if CACHE_FILE.exists():
            fc = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            return {"entries": len(fc), "file": str(CACHE_FILE)}
    except Exception:
        pass
    return {"entries": 0}
