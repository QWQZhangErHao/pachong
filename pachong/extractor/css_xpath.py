"""High-performance CSS/XPath selector extractor — the PRIMARY extraction engine.

This is the workhorse. It applies cached CSS/XPath rules to HTML at native
speed (lxml C extensions). No LLM calls on the hot path.

Rules are pre-compiled and cached. When rules fail (ElementNotFound),
the llm_healer is invoked asynchronously behind a Redlock.
"""

from __future__ import annotations

import time

import structlog
from lxml import html

from pachong.core.models import ExtractionRule
from pachong.extractor.base import BaseExtractor, ExtractedField, ExtractionResult

logger = structlog.get_logger(__name__)

# Default extraction rules for common e-commerce sites
# These serve as the fallback when no cached rules exist
DEFAULT_PRODUCT_RULES: dict[str, list[dict]] = {
    "generic": [
        {"field": "title", "selector": "h1", "type": "css", "attr": None},
        {"field": "title", "selector": "//h1//text()", "type": "xpath", "attr": None},
        {"field": "title", "selector": "meta[property='og:title']", "type": "css", "attr": "content"},
        {"field": "description", "selector": "meta[name='description']", "type": "css", "attr": "content"},
        {"field": "description", "selector": "meta[property='og:description']", "type": "css", "attr": "content"},
        {"field": "price", "selector": "[class*='price']", "type": "css", "attr": None},
        {"field": "price", "selector": "meta[property='product:price:amount']", "type": "css", "attr": "content"},
        {"field": "currency", "selector": "meta[property='product:price:currency']", "type": "css", "attr": "content"},
        {"field": "image", "selector": "meta[property='og:image']", "type": "css", "attr": "content"},
        {"field": "sku", "selector": "[data-sku], [itemprop='sku']", "type": "css", "attr": None},
        {"field": "brand", "selector": "[itemprop='brand']", "type": "css", "attr": None},
        {"field": "brand", "selector": "meta[property='product:brand']", "type": "css", "attr": "content"},
        {"field": "availability", "selector": "[itemprop='availability']", "type": "css", "attr": "content"},
        {"field": "category", "selector": "[class*='breadcrumb'] a:last-child", "type": "css", "attr": None},
    ],
    "amazon": [
        {"field": "title", "selector": "#productTitle", "type": "css", "attr": None},
        {"field": "price", "selector": ".a-price .a-offscreen", "type": "css", "attr": None},
        {"field": "price", "selector": "#priceblock_dealprice, #priceblock_ourprice", "type": "css", "attr": None},
        {"field": "rating", "selector": "#acrPopover [data-hook='rating-out-of-text']", "type": "css", "attr": None},
        {"field": "rating", "selector": "span[data-hook='rating-out-of-text']", "type": "css", "attr": None},
        {"field": "review_count", "selector": "#acrCustomerReviewText", "type": "css", "attr": None},
        {"field": "brand", "selector": "#bylineInfo", "type": "css", "attr": None},
        {"field": "image", "selector": "#landingImage, #imgTagWrapperId img", "type": "css", "attr": "src"},
    ],
}


class CssXPathExtractor(BaseExtractor):
    """High-speed CSS/XPath-based extractor backed by lxml.

    Applies pre-cached rules. This is the primary extraction path —
    fast, cheap, and deterministic.
    """

    name = "css_xpath"

    def __init__(self, rules: list[ExtractionRule] | None = None) -> None:
        self._rules: list[ExtractionRule] = rules or []
        self._default_config: dict[str, list[dict]] = DEFAULT_PRODUCT_RULES

    def set_rules(self, rules: list[ExtractionRule]) -> None:
        """Update the active rule set (e.g., after llm_healer generates new rules)."""
        self._rules = rules

    async def extract(self, html_str: str, url: str, **kwargs) -> ExtractionResult:
        result = ExtractionResult(url=url)
        start = time.monotonic()

        try:
            doc = html.fromstring(html_str)
        except Exception as e:
            result.errors.append(f"HTML parse error: {e}")
            return result

        # Phase 1: Apply cached/specific rules
        for rule in self._rules:
            try:
                values = self._apply_rule(doc, rule)
                for val in values:
                    if val and result.get(rule.field_name) is None:
                        result.fields.append(ExtractedField(
                            name=rule.field_name,
                            value=val,
                            selector_used=rule.selector,
                            source="css_xpath_rule",
                            confidence=0.95,
                        ))
            except Exception:
                continue

        # Phase 2: Apply default generic rules for remaining fields
        default_rules = self._default_config.get("generic", [])
        # Also check domain-specific defaults
        from urllib.parse import urlparse
        domain = urlparse(url).hostname or ""
        for site_key, site_rules in self._default_config.items():
            if site_key != "generic" and site_key in domain:
                default_rules = site_rules + default_rules
                break

        for rule_def in default_rules:
            if result.get(rule_def["field"]) is not None:
                continue  # Already extracted
            try:
                val = self._apply_simple_rule(doc, rule_def)
                if val:
                    result.fields.append(ExtractedField(
                        name=rule_def["field"],
                        value=val,
                        selector_used=rule_def["selector"],
                        source="css_xpath_default",
                        confidence=0.7,
                    ))
            except Exception:
                continue

        result.extraction_time_ms = (time.monotonic() - start) * 1000
        if result.fields:
            result.success = True
            result.extractors_used.append(self.name)

        return result

    def _apply_rule(self, doc, rule: ExtractionRule) -> list[str]:
        """Apply a single ExtractionRule to the document."""
        if rule.selector_type == "css":
            elements = doc.cssselect(rule.selector)
        elif rule.selector_type == "xpath":
            elements = doc.xpath(rule.selector)
        else:
            return []

        values = []
        for el in elements:
            if rule.attribute:
                val = el.get(rule.attribute)
                if val:
                    values.append(val.strip() if isinstance(val, str) else str(val))
            else:
                text = self._get_text(el)
                if text:
                    values.append(text)

        return values

    def _apply_simple_rule(self, doc, rule_def: dict) -> str | None:
        """Apply a rule defined as a simple dict."""
        selector = rule_def["selector"]
        selector_type = rule_def.get("type", "css")
        attr = rule_def.get("attr")

        if selector_type == "css":
            elements = doc.cssselect(selector)
        elif selector_type == "xpath":
            elements = doc.xpath(selector)
        else:
            return None

        if not elements:
            return None

        el = elements[0]
        if attr:
            val = el.get(attr)
            return val.strip() if isinstance(val, str) else str(val) if val else None
        else:
            return self._get_text(el)

    def _get_text(self, el) -> str:
        """Extract clean text from an element."""
        text = el.text_content() if hasattr(el, "text_content") else str(el)
        if isinstance(text, str):
            return " ".join(text.split())  # Normalize whitespace
        return str(text)


# Note: lxml is used for CSS/XPath selection. If unavailable, fall back
# to re/pure-Python parsing. Add to pyproject.toml:
# lxml>=5.3
