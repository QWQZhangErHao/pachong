"""JSON-LD / Schema.org structured data extractor.

Many e-commerce sites embed Product, Offer, and Organization data in
JSON-LD script tags. This is the FASTEST extraction path — no DOM
parsing needed, just JSON decode.
"""

from __future__ import annotations

import json
import re
from typing import Any

import structlog

from pachong.extractor.base import BaseExtractor, ExtractedField, ExtractionResult

logger = structlog.get_logger(__name__)

JSON_LD_RE = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)

SCHEMA_PRODUCT_TYPES = {"Product", "ProductGroup", "IndividualProduct", "ProductModel"}
SCHEMA_OFFER_TYPES = {"Offer", "AggregateOffer"}
SCHEMA_ORG_TYPES = {"Organization", "Brand"}


class SchemaOrgExtractor(BaseExtractor):
    """Extracts JSON-LD structured data from script tags."""

    name = "schema_org"

    async def extract(self, html: str, url: str, **kwargs) -> ExtractionResult:
        result = ExtractionResult(url=url)

        try:
            blocks = self._find_json_ld_blocks(html)
            if not blocks:
                return result

            for block in blocks:
                data = self._parse_json_ld(block)
                if not data:
                    continue

                # Handle @graph (multiple entities in one block)
                if "@graph" in data:
                    for item in data["@graph"]:
                        self._extract_from_node(item, result)
                else:
                    self._extract_from_node(data, result)

            if result.fields:
                result.success = True
                result.extractors_used.append(self.name)
        except Exception as e:
            result.errors.append(f"schema_org: {e}")

        return result

    def _find_json_ld_blocks(self, html: str) -> list[str]:
        return JSON_LD_RE.findall(html)

    def _parse_json_ld(self, text: str) -> dict | None:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def _extract_from_node(self, node: dict, result: ExtractionResult) -> None:
        node_type = node.get("@type", "")

        # Normalize: handle lists
        if isinstance(node_type, list):
            node_type = node_type[0] if node_type else ""

        # Product
        if node_type in SCHEMA_PRODUCT_TYPES:
            self._extract_product(node, result)

        # Offer (price)
        if node_type in SCHEMA_OFFER_TYPES:
            self._extract_offer(node, result)

        # Organization / Brand
        if node_type in SCHEMA_ORG_TYPES:
            self._extract_organization(node, result)

    def _extract_product(self, node: dict, result: ExtractionResult) -> None:
        _add_if(result, "title", node.get("name"), "schema_org")
        _add_if(result, "description", node.get("description"), "schema_org")
        _add_if(result, "sku", node.get("sku"), "schema_org")
        _add_if(result, "brand", _nested(node, "brand", "name"), "schema_org")
        _add_if(result, "image", _first(node.get("image")), "schema_org")
        _add_if(result, "category", _nested(node, "category", "name") or node.get("category"), "schema_org")
        _add_if(result, "upc", node.get("gtin12") or node.get("upc"), "schema_org")
        _add_if(result, "ean", node.get("gtin13") or node.get("ean"), "schema_org")

        # Rating
        if "aggregateRating" in node:
            rating = node["aggregateRating"]
            _add_if(result, "rating_value", rating.get("ratingValue"), "schema_org")
            _add_if(result, "review_count", rating.get("reviewCount"), "schema_org")

        # Offers (nested inside Product)
        if "offers" in node:
            offers = node["offers"]
            if isinstance(offers, dict):
                self._extract_offer(offers, result)
            elif isinstance(offers, list):
                self._extract_offer(offers[0], result)

    def _extract_offer(self, node: dict, result: ExtractionResult) -> None:
        _add_if(result, "price", node.get("price"), "schema_org")
        _add_if(result, "currency", node.get("priceCurrency"), "schema_org")
        _add_if(result, "availability", _nested(node, "availability", "name") or node.get("availability"), "schema_org")
        _add_if(result, "price_valid_until", node.get("priceValidUntil"), "schema_org")

    def _extract_organization(self, node: dict, result: ExtractionResult) -> None:
        _add_if(result, "brand", node.get("name"), "schema_org")


def _add_if(result: ExtractionResult, name: str, value: Any, source: str) -> None:
    """Add a field only if it has a non-None value and doesn't already exist."""
    if value is not None and value != "" and result.get(name) is None:
        result.fields.append(ExtractedField(name=name, value=value, source=source))


def _nested(node: dict, *keys: str) -> Any:
    """Safely traverse nested dict keys."""
    current = node
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        elif isinstance(current, list) and current:
            current = current[0].get(key) if isinstance(current[0], dict) else None
        else:
            return None
    return current


def _first(value: Any) -> Any:
    """Return first element if list, else the value."""
    if isinstance(value, list) and value:
        return value[0] if isinstance(value[0], str) else value[0].get("url", str(value[0]))
    return value
