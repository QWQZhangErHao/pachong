"""Vision-based multimodal extraction using GPT-4V or similar.

THE LAST RESORT: Only used when:
1. JSON-LD not present
2. CSS/XPath rules all failed
3. LLM healer couldn't generate working rules
4. Adaptive IE returned low confidence

Takes a screenshot from S3 and sends it to a multimodal LLM for extraction.
EXPENSIVE — used sparingly.
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any

import structlog

from pachong.extractor.base import BaseExtractor, ExtractedField, ExtractionResult

logger = structlog.get_logger(__name__)

MULTIMODAL_PROMPT = """Extract product information from this e-commerce page screenshot.
Return ONLY a JSON object with these fields (omit if not visible):
{
    "title": "product name",
    "price": 29.99,
    "currency": "USD",
    "description": "product description",
    "brand": "brand name",
    "sku": "product ID",
    "availability": "in_stock or out_of_stock",
    "rating_value": 4.5,
    "review_count": 1234,
    "variants": [{"name": "color", "value": "red"}, {"name": "size", "value": "large"}]
}

Rules:
- For price: extract the current selling price as a NUMBER, not a string
- Do NOT include the currency symbol in the price field
- For availability: infer from text like "In Stock", "Out of Stock", "Add to Cart"
- Be precise — only include information VISIBLE in the screenshot
"""


class MultimodalExtractor(BaseExtractor):
    """Extract product data from screenshots using multimodal LLMs.

    This is the most expensive extraction method. Use only as fallback.
    """

    name = "multimodal"

    def __init__(self, model: str = "gpt-4o") -> None:
        self.model = model

    async def extract(self, html: str, url: str, **kwargs) -> ExtractionResult:
        result = ExtractionResult(url=url)
        start = time.monotonic()

        screenshot_bytes = kwargs.get("screenshot_bytes")
        screenshot_key = kwargs.get("screenshot_key")

        if not screenshot_bytes and not screenshot_key:
            result.errors.append("multimodal: no screenshot provided")
            return result

        try:
            # Load screenshot from S3 if key provided
            if screenshot_key and not screenshot_bytes:
                from pachong.storage.blob.s3_client import download_bytes
                screenshot_bytes = await download_bytes(screenshot_key)

            if not screenshot_bytes:
                result.errors.append("multimodal: screenshot data is empty")
                return result

            # Encode as base64
            image_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
            data_url = f"data:image/png;base64,{image_b64}"

            content = await self._call_multimodal_llm(data_url)

            if content:
                data = self._parse_response(content)
                for name, value in data.items():
                    if value is not None:
                        result.fields.append(ExtractedField(
                            name=name,
                            value=value,
                            source=self.name,
                            confidence=0.85,
                        ))

            result.extraction_time_ms = (time.monotonic() - start) * 1000
            if result.fields:
                result.success = True
                result.extractors_used.append(self.name)

        except Exception as e:
            result.errors.append(f"multimodal: {e}")
            logger.error("multimodal.extraction_failed", url=url, error=str(e))

        return result

    async def _call_multimodal_llm(self, image_data_url: str) -> str | None:
        """Call a multimodal LLM with the screenshot."""
        try:
            import importlib

            if importlib.util.find_spec("openai"):
                import openai

                client = openai.AsyncOpenAI()
                response = await client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": MULTIMODAL_PROMPT},
                                {"type": "image_url", "image_url": {"url": image_data_url}},
                            ],
                        }
                    ],
                    max_tokens=2000,
                    temperature=0.1,
                )
                return response.choices[0].message.content
            else:
                logger.warning("multimodal.no_openai_sdk")
                return None
        except Exception as e:
            logger.error("multimodal.api_error", error=str(e))
            return None

    def _parse_response(self, content: str | None) -> dict[str, Any]:
        if not content:
            return {}

        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:]) if lines[0].startswith("```") else content
            if content.endswith("```"):
                content = content[:-3]

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Try to find JSON object
            import re
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            return {}
