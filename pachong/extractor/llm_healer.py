"""LLM-based extraction rule repair with Redlock distributed lock protection.

THE CRITICAL DESIGN:
When extraction rules fail (ElementNotFound), this module:
1. Acquires a Redlock for {domain}:{path_pattern}
2. Only ONE worker across the entire cluster gets the lock
3. That worker downloads the raw HTML from S3 and calls the LLM
4. LLM analyzes the HTML and generates new CSS/XPath rules
5. New rules are cached in Redis (other workers now see them)
6. Lock is released

Without Redlock: 1000 workers each call LLM for the same broken page
→ $100s in API costs per rule change.

With Redlock: 1 LLM call per rule change → <$1.
"""

from __future__ import annotations

import json

import structlog

from pachong.core.models import ExtractionRule
from pachong.extractor.rule_manager import cache_rules

logger = structlog.get_logger(__name__)

LLM_HEALER_PROMPT = """You are an expert web scraping engineer. The XPath/CSS selectors
used to extract product data from an e-commerce page have stopped working
because the page structure changed.

Given the HTML snippet below, generate new CSS selectors (or XPath)
to extract the following fields:
- title (product name)
- price (current selling price, as a number)
- currency (ISO code: USD, EUR, etc.)
- description (product description text)
- brand (manufacturer or brand name)
- sku (product identifier / stock keeping unit)
- image (main product image URL)
- availability (in_stock / out_of_stock)
- rating_value (numeric rating, e.g. 4.5)
- review_count (number of reviews)

Rules for selectors:
1. Use CSS selectors (preferred) or XPath.
2. Prefer data attributes ([data-testid], [data-sku]) over class names.
3. Prefer semantic elements (h1, meta[property], [itemprop]) over div soup.
4. If a field is not present, omit it.
5. For price: strip currency symbols, return only the number.

IMPORTANT: Do NOT include the full price (e.g. "$19.99") in the selector.
The text content may include the currency symbol.

Return ONLY a JSON array of objects with fields: field_name, selector_type ("css" or "xpath"), selector, attribute (null if text content).

HTML:
{html_snippet}

Fields to extract: {fields_requested}
"""


class LLMHealer:
    """Manages LLM-based extraction rule repair with Redlock coordination."""

    def __init__(
        self,
        model: str = "gpt-4o",
        redlock_ttl_ms: int = 30_000,
        retry_count: int = 3,
        retry_delay_ms: int = 500,
        lock_wait_timeout: float = 0.3,
    ) -> None:
        self.model = model
        self.redlock_ttl_ms = redlock_ttl_ms
        self.retry_count = retry_count
        self.retry_delay_ms = retry_delay_ms
        self.lock_wait_timeout = lock_wait_timeout

    async def _try_acquire_setnx(self, resource: str, ttl_ms: int) -> str | None:
        """Simple setnx-based lock. Returns sentinel 'NO_REDIS' if Redis unavailable."""
        import uuid
        try:
            from pachong.storage.redis_.client import get_redis, is_degraded
        except Exception:
            return "NO_REDIS"
        try:
            if is_degraded():
                return "NO_REDIS"
            redis = get_redis()
        except (RuntimeError, Exception):
            return "NO_REDIS"
        try:
            if redis is None:
                return "NO_REDIS"
            token = str(uuid.uuid4())
            acquired = await redis.set(f"lock:{resource}", token, nx=True, px=ttl_ms)
            return token if acquired else None
        except Exception:
            return "NO_REDIS"
            return None

    async def _release_setnx(self, resource: str, token: str) -> None:
        try:
            from pachong.storage.redis_.client import get_redis
            redis = get_redis()
            lua = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"
            await redis.eval(lua, 1, f"lock:{resource}", token)
        except Exception:
            pass

    async def heal_rules(
        self,
        domain: str,
        path_pattern: str,
        html: str,
        failed_fields: list[str] | None = None,
    ) -> list[ExtractionRule] | None:
        """Attempt to heal rules with setnx lock + fast return if Redis unavailable."""
        # Fast-path: skip if LLM circuit breaker is open
        try:
            from pachong.resilience.circuit_breaker import get_llm_breaker
            if get_llm_breaker().is_open:
                return None
        except Exception:
            pass

        lock_resource = f"healer:{domain}:{path_pattern}"
        import asyncio

        # Try setnx lock with bounded wait (skip entirely if Redis unavailable)
        lock_token = await self._try_acquire_setnx(lock_resource, self.redlock_ttl_ms)
        if lock_token == "NO_REDIS":
            return None  # Redis not available — skip LLM healer
        if lock_token is None:
            # Contention: brief bounded wait
            deadline = asyncio.get_event_loop().time() + self.lock_wait_timeout
            while asyncio.get_event_loop().time() < deadline:
                await asyncio.sleep(0.05)
                lock_token = await self._try_acquire_setnx(lock_resource, self.redlock_ttl_ms)
                if lock_token and lock_token != "NO_REDIS":
                    break

        if lock_token is None or lock_token == "NO_REDIS":
            logger.info("llm_healer.lock_timeout", domain=domain)
            return None  # Direct fail, no starvation

        try:
            logger.info("llm_healer.healing_started", domain=domain, pattern=path_pattern)
            rules = await self._call_llm(html, failed_fields)
            if rules:
                await cache_rules(domain, path_pattern, rules)
                logger.info("llm_healer.healing_success", domain=domain, rule_count=len(rules))
                return rules
            return None
        except Exception as e:
            logger.error("llm_healer.healing_failed", domain=domain, error=str(e))
            return None
        finally:
            await self._release_setnx(lock_resource, lock_token)

    async def _call_llm(
        self,
        html: str,
        failed_fields: list[str] | None = None,
    ) -> list[ExtractionRule] | None:
        """Call the LLM to analyze HTML and generate new extraction rules.

        This is the ONLY place in the system that calls an LLM API.
        It happens asynchronously, behind a Redlock, and only on rule failure.
        """
        # Truncate HTML to avoid token limits (first 15KB is usually enough
        # for all the structural elements we need)
        html_snippet = html[:15_000] if len(html) > 15_000 else html

        fields_requested = failed_fields or [
            "title", "price", "currency", "description", "brand",
            "sku", "image", "availability", "rating_value", "review_count",
        ]

        prompt = LLM_HEALER_PROMPT.format(
            html_snippet=html_snippet,
            fields_requested=", ".join(fields_requested),
        )

        try:
            # Try using litellm for provider-agnostic LLM calls
            import importlib

            if importlib.util.find_spec("litellm"):
                import litellm

                response = await litellm.acompletion(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=2000,
                    temperature=0.1,
                )
                content = response.choices[0].message.content
            elif importlib.util.find_spec("openai"):
                import openai

                client = openai.AsyncOpenAI()
                response = await client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=2000,
                    temperature=0.1,
                )
                content = response.choices[0].message.content
            else:
                logger.error("llm_healer.no_llm_library")
                return None

            return self._parse_llm_response(content)
        except Exception as e:
            logger.error("llm_healer.api_error", error=str(e))
            return None

    def _parse_llm_response(self, content: str | None) -> list[ExtractionRule] | None:
        """Parse JSON response from LLM into ExtractionRule objects."""
        if not content:
            return None

        # Extract JSON from response (may be wrapped in ```json blocks)
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:]) if lines[0].startswith("```") else content
            if content.endswith("```"):
                content = content[:-3]

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            # Try to find JSON array in the response
            import re

            match = re.search(r"\[.*\]", content, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                except json.JSONDecodeError:
                    return None
            else:
                return None

        if not isinstance(data, list):
            return None

        rules = []
        for item in data:
            try:
                rules.append(ExtractionRule(
                    domain="",  # Will be set by caller
                    path_pattern="",
                    field_name=item["field_name"],
                    selector_type=item["selector_type"],
                    selector=item["selector"],
                    attribute=item.get("attribute"),
                ))
            except (KeyError, TypeError):
                continue

        return rules
