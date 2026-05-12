"""Adaptive IE (Information Extraction) model extractor.

Uses a pre-trained or fine-tuned model to extract entities, attributes,
and relationships from unstructured product detail pages.

This is a specialized mid-tier extractor: more capable than CSS/XPath
(handles unseen page structures) but cheaper than multimodal (no vision).
Uses a small, fast NER/IE model rather than a large LLM.
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from pachong.extractor.base import BaseExtractor, ExtractedField, ExtractionResult

logger = structlog.get_logger(__name__)


class AdaptiveIEExtractor(BaseExtractor):
    """Adaptive information extraction using lightweight ML models.

    Falls back gracefully to heuristics if models are unavailable.
    """

    name = "adaptive_ie"

    def __init__(self) -> None:
        self._model = None
        self._model_loaded = False

    async def _load_model(self) -> bool:
        """Lazy-load the IE model on first use."""
        if self._model_loaded:
            return self._model is not None

        try:
            # Try spaCy for NER-based extraction
            import importlib
            if importlib.util.find_spec("spacy"):
                import spacy
                try:
                    self._model = spacy.load("en_core_web_sm")
                except OSError:
                    # Model not downloaded — skip
                    pass
        except Exception:
            pass

        self._model_loaded = True
        return self._model is not None

    async def extract(self, html_str: str, url: str, **kwargs) -> ExtractionResult:
        result = ExtractionResult(url=url)
        start = time.monotonic()

        try:
            # Extract visible text from HTML
            text = self._extract_text(html_str)
            if not text.strip():
                return result

            if await self._load_model():
                fields = self._extract_with_spacy(text)
                for name, value in fields.items():
                    if value:
                        result.fields.append(ExtractedField(
                            name=name,
                            value=value,
                            source=self.name,
                            confidence=0.7,
                        ))

            # Heuristic extraction (always runs, even without model)
            heuristic_fields = self._heuristic_extract(text, html_str)
            for name, value in heuristic_fields.items():
                if value and result.get(name) is None:
                    result.fields.append(ExtractedField(
                        name=name,
                        value=value,
                        source=f"{self.name}_heuristic",
                        confidence=0.5,
                    ))

            result.extraction_time_ms = (time.monotonic() - start) * 1000
            if result.fields:
                result.success = True
                result.extractors_used.append(self.name)

        except Exception as e:
            result.errors.append(f"adaptive_ie: {e}")

        return result

    def _extract_with_spacy(self, text: str) -> dict[str, Any]:
        """Use spaCy NER to find entities."""
        if not self._model:
            return {}

        doc = self._model(text[:100_000])  # Truncate for performance
        fields: dict[str, Any] = {}

        # Organizations → brand/manufacturer
        orgs = [ent.text for ent in doc.ents if ent.label_ == "ORG"]
        if orgs:
            fields["brand"] = orgs[0]

        # Money → price
        money = [ent.text for ent in doc.ents if ent.label_ == "MONEY"]
        if money:
            price_str = money[0].replace("$", "").replace("€", "").replace(",", "")
            try:
                fields["price"] = float(price_str)
            except ValueError:
                fields["price"] = money[0]

        # Products → title
        products = [ent.text for ent in doc.ents if ent.label_ == "PRODUCT"]
        if products:
            fields["title"] = products[0]

        return fields

    def _heuristic_extract(self, text: str, html: str) -> dict[str, Any]:
        """Heuristic extraction using regex patterns (no ML)."""
        import re

        fields: dict[str, Any] = {}

        # Price patterns
        price_patterns = [
            r'\$\s?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',
            r'€\s?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',
            r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s?(?:USD|EUR|GBP)',
        ]
        for pat in price_patterns:
            match = re.search(pat, text)
            if match:
                try:
                    fields["price"] = float(match.group(1).replace(",", ""))
                except ValueError:
                    fields["price"] = match.group(1)
                break

        # SKU patterns
        sku_patterns = [
            r'SKU[:\s]*([A-Z0-9\-]{4,})',
            r'Item\s*#[:\s]*([A-Z0-9\-]{4,})',
            r'Model[:\s]*#?[:\s]*([A-Z0-9\-]{4,})',
        ]
        for pat in sku_patterns:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                fields["sku"] = match.group(1).strip()
                break

        # Rating
        rating_match = re.search(r'(\d\.?\d?)\s*(?:out of|stars?|rating)', text, re.IGNORECASE)
        if rating_match:
            try:
                fields["rating_value"] = float(rating_match.group(1))
            except ValueError:
                pass

        # Review count
        review_match = re.search(r'(\d{1,3}(?:,\d{3})*)\s*(?:review|rating)', text, re.IGNORECASE)
        if review_match:
            fields["review_count"] = review_match.group(1).replace(",", "")

        return fields

    def _extract_text(self, html_str: str) -> str:
        """Extract visible text from HTML (simple approach)."""
        import re

        # Remove scripts and styles
        text = re.sub(r'<script[^>]*>.*?</script>', '', html_str, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        # Remove tags
        text = re.sub(r'<[^>]+>', ' ', text)
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        return text
