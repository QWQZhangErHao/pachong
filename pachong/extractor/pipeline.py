"""Extraction pipeline orchestrator.

Coordinates the extraction hierarchy:
1. JSON-LD / Schema.org (free, always try first)
2. Cached CSS/XPath rules (primary, fast)
3. Rule failure → LLM Healer (Redlock, async repair)
4. Adaptive IE (mid-tier, ML-based)
5. Multimodal (expensive, last resort)

The pipeline respects the cost hierarchy:
  Schema.org ≈ CSS/XPath << Adaptive IE << LLM Healer << Multimodal
"""

from __future__ import annotations

import asyncio
import time

import structlog

from pachong.core.models import ExtractionRule
from pachong.core.settings import Settings
from pachong.extractor.base import ExtractionResult
from pachong.extractor.css_xpath import CssXPathExtractor
from pachong.extractor.llm_healer import LLMHealer
from pachong.extractor.rule_manager import get_rules
from pachong.extractor.schema_org import SchemaOrgExtractor

logger = structlog.get_logger(__name__)


class ExtractionPipeline:
    """Orchestrates all extractors in cost-ascending order."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.schema_org = SchemaOrgExtractor()
        self.css_xpath = CssXPathExtractor()
        self.llm_healer = LLMHealer(
            model=settings.extractor.llm_healer_model,
            redlock_ttl_ms=settings.extractor.redlock_ttl_ms,
            retry_count=settings.extractor.redlock_retry_count,
            retry_delay_ms=settings.extractor.redlock_retry_delay_ms,
        )
        self._adaptive = None  # Lazy import
        self._multimodal = None

    async def extract(
        self,
        html: str,
        url: str,
        domain: str,
        screenshot_bytes: bytes | None = None,
        screenshot_s3_key: str | None = None,
        force_multimodal: bool = False,
    ) -> ExtractionResult:
        """Run the extraction pipeline and return structured results.

        Args:
            html: Raw HTML content
            url: Source URL
            domain: Target domain (for rule lookup)
            screenshot_bytes: Optional screenshot (for multimodal fallback)
            screenshot_s3_key: Optional S3 key for screenshot
            force_multimodal: Skip straight to multimodal (debug/testing)

        Returns:
            ExtractionResult with extracted fields and metadata
        """
        start = time.monotonic()
        final_result = ExtractionResult(url=url)

        if force_multimodal:
            return await self._tier_multimodal(final_result, html, url, screenshot_bytes, screenshot_s3_key, start)

        # ── Tier 1-2 parallel: Schema + CSS/XPath + Adaptive IE ──
        # Try to load cached rules (non-blocking)
        try:
            rules = await get_rules(domain, url)
            if rules:
                self.css_xpath.set_rules(rules)
        except RuntimeError:
            pass

        # Run all three extractors concurrently, take first with >= 4 fields
        parallel_results = await asyncio.gather(
            self.schema_org.extract(html, url),
            self.css_xpath.extract(html, url),
            self._try_adaptive(html, url),
            return_exceptions=True,
        )

        best_count = 0
        for r in parallel_results:
            if isinstance(r, ExtractionResult):
                self._merge(final_result, r)
                field_count = len([f for f in final_result.fields])
                if field_count > best_count:
                    best_count = field_count
            if best_count >= 4:
                break

        missing = self._missing_fields(final_result)
        if not missing:
            final_result.extraction_time_ms = (time.monotonic() - start) * 1000
            final_result.extractors_used.append("pipeline_parallel")
            return final_result

        logger.debug("pipeline.missing_fields", fields=missing)

        # ── Tier 3: LLM Healer (async rule repair) — with cache + REDLOCK ──
        if self.settings.extractor.llm_healer_enabled:
            try:
                from urllib.parse import urlparse
                path = urlparse(url).path
                path_pattern = self._infer_path_pattern(path)

                # Check LLM cache first
                from pachong.extractor.llm_cache import cache_rules_result, get_cached_rules
                cached = await get_cached_rules(domain, html)
                if cached:
                    healed_rules = [self._dict_to_rule(r) for r in cached]
                    logger.debug("pipeline.llm_cache_hit", domain=domain)
                else:
                    healed_rules = await self.llm_healer.heal_rules(
                        domain=domain,
                        path_pattern=path_pattern,
                        html=html,
                        failed_fields=missing,
                    )
                    if healed_rules:
                        await cache_rules_result(
                            domain, html,
                            [{"field_name": r.field_name, "selector_type": r.selector_type,
                              "selector": r.selector, "attribute": r.attribute} for r in healed_rules]
                        )

                if healed_rules:
                    self.css_xpath.set_rules(healed_rules)
                    healed_result = await self.css_xpath.extract(html, url)
                    self._merge(final_result, healed_result)

                    missing = self._missing_fields(final_result)
                    if not missing:
                        final_result.extraction_time_ms = (time.monotonic() - start) * 1000
                        final_result.extractors_used.append("pipeline")
                        return final_result
            except RuntimeError:
                pass  # Redis not available — skip LLM healer

        # ── Tier 4: Adaptive IE (ML-based) ──
        if self._adaptive is None:
            from pachong.extractor.adaptive import AdaptiveIEExtractor
            self._adaptive = AdaptiveIEExtractor()

        adaptive_result = await self._adaptive.extract(html, url)
        self._merge(final_result, adaptive_result)
        logger.debug("pipeline.tier4_adaptive", success=adaptive_result.success)

        missing = self._missing_fields(final_result)
        if not missing:
            final_result.extraction_time_ms = (time.monotonic() - start) * 1000
            final_result.extractors_used.append("pipeline")
            return final_result

        # ── Tier 5: Multimodal (vision LLM) — LAST RESORT ──
        return await self._tier_multimodal(final_result, html, url, screenshot_bytes, screenshot_s3_key, start)

    async def _try_adaptive(self, html: str, url: str) -> ExtractionResult:
        """Run adaptive IE extractor safely, returns empty result on failure."""
        try:
            if self._adaptive is None:
                from pachong.extractor.adaptive import AdaptiveIEExtractor
                self._adaptive = AdaptiveIEExtractor()
            return await self._adaptive.extract(html, url)
        except Exception:
            return ExtractionResult(url=url)

    @staticmethod
    def _dict_to_rule(d: dict) -> ExtractionRule:
        return ExtractionRule(
            domain="", path_pattern="",
            field_name=d["field_name"],
            selector_type=d.get("selector_type", "css"),
            selector=d["selector"],
            attribute=d.get("attribute"),
        )

    async def _tier_multimodal(
        self,
        result: ExtractionResult,
        html: str,
        url: str,
        screenshot_bytes: bytes | None,
        screenshot_s3_key: str | None,
        start_time: float,
    ) -> ExtractionResult:
        if self._multimodal is None:
            from pachong.extractor.multimodal import MultimodalExtractor
            self._multimodal = MultimodalExtractor(model=self.settings.extractor.multimodal_model)

        mm_result = await self._multimodal.extract(
            html, url,
            screenshot_bytes=screenshot_bytes,
            screenshot_key=screenshot_s3_key,
        )
        self._merge(result, mm_result)
        result.extraction_time_ms = (time.monotonic() - start_time) * 1000
        result.extractors_used.append("pipeline")
        return result

    def _merge(self, target: ExtractionResult, source: ExtractionResult) -> None:
        """Merge fields from source into target, keeping higher-confidence values."""
        target.errors.extend(source.errors)
        if source.success:
            target.success = True
        target.extractors_used.extend(source.extractors_used)

        for field in source.fields:
            existing = target.get(field.name)
            if existing is None or field.confidence > 0.7:
                # Remove old field if present
                target.fields = [f for f in target.fields if f.name != field.name]
                target.fields.append(field)

    def _missing_fields(self, result: ExtractionResult) -> list[str]:
        """Return list of field names still missing or with low confidence."""
        critical = ["title", "price"]
        important = ["brand", "sku", "description", "image"]
        all_required = critical + important

        missing = []
        for field_name in all_required:
            val = result.get(field_name)
            if val is None:
                if field_name in critical:
                    missing.append(field_name)  # Always require critical
                else:
                    missing.append(field_name)

        return missing

    def _infer_path_pattern(self, path: str) -> str:
        """Infer a path pattern from a URL path.

        Examples:
            /products/abc-123 → /products/{slug}
            /dp/B09XYZ → /dp/{sku}
            /category/electronics → /category/{category}
            /item/12345 → /item/{id}
        """
        import re

        parts = path.strip("/").split("/")

        inferred = []
        for i, part in enumerate(parts):
            # Heuristic: if the part looks like an ID, replace with placeholder
            if re.match(r"^[A-Z0-9]{8,}$", part):
                inferred.append("{sku}")
            elif re.match(r"^[a-z0-9]+[-][a-z0-9-]+$", part):
                inferred.append("{slug}")
            elif re.match(r"^\d+$", part):
                inferred.append("{id}")
            elif i == len(parts) - 1 and re.match(r"^[a-zA-Z0-9_-]+$", part):
                inferred.append("{slug}")
            else:
                inferred.append(part)

        return "/" + "/".join(inferred)
