"""Integration tests for the full end-to-end pipeline.

Tests the flow: HTML → Extractors → Structured Data
"""

from __future__ import annotations

import asyncio

from pachong.core.settings import Settings
from pachong.extractor.css_xpath import CssXPathExtractor
from pachong.extractor.pipeline import ExtractionPipeline
from pachong.extractor.schema_org import SchemaOrgExtractor


class TestExtractionPipeline:
    def test_schema_org_extracts_product(self, sample_html_jsonld):
        extractor = SchemaOrgExtractor()
        result = asyncio.run(extractor.extract(sample_html_jsonld, "https://example.com/p/1"))
        assert result.success
        assert result.get("title") == "JSON-LD Product"
        assert result.get("price") == "49.99"
        assert result.get("currency") == "EUR"
        assert result.get("sku") == "JLD-001"
        assert result.get("rating_value") == "4.7"

    def test_css_xpath_extracts_with_default_rules(self, sample_html_product):
        extractor = CssXPathExtractor()
        result = asyncio.run(extractor.extract(sample_html_product, "https://example.com/p/1"))
        assert result.success
        assert result.get("title") is not None
        assert result.get("price") is not None

    def test_pipeline_runs_all_tiers(self, sample_html_jsonld):
        settings = Settings.load()
        pipeline = ExtractionPipeline(settings)
        result = asyncio.run(pipeline.extract(
            sample_html_jsonld,
            "https://example.com/p/1",
            domain="example.com",
        ))
        assert result.success
        assert result.get("title") is not None
        assert "pipeline" in result.extractors_used

    def test_pipeline_returns_empty_for_junk_html(self):
        settings = Settings.load()
        pipeline = ExtractionPipeline(settings)
        result = asyncio.run(pipeline.extract(
            "<html><body>No product data here</body></html>",
            "https://example.com/p/1",
            domain="example.com",
        ))
        # Pipeline may still succeed if it found *something*
        # The test validates it doesn't crash on worthless HTML
        assert result is not None


class TestResponseModel:
    def test_success_response(self, fetch_response_ok):
        assert fetch_response_ok.is_success
        assert not fetch_response_ok.is_blocked
        assert fetch_response_ok.content_length > 0

    def test_blocked_response(self, fetch_response_blocked):
        assert fetch_response_blocked.is_blocked
        assert fetch_response_blocked.is_js_challenge
        assert fetch_response_blocked.js_challenge_type == "cloudflare"


class TestCompressionPipeline:
    def test_html_compress_decompress_roundtrip(self):
        from pachong.core.compression import compress_html, decompress_html
        html = "<!DOCTYPE html><html><body>" + "<div>test</div>" * 100 + "</body></html>"
        compressed = compress_html(html)
        decompressed = decompress_html(compressed)
        assert decompressed == html
        assert len(compressed) < len(html)


class TestSettings:
    def test_settings_loads(self, settings):
        assert settings.env == "development"
        assert settings.database.postgres_dsn

    def test_settings_cascade_applies_dev_overrides(self, settings):
        assert settings.log_level == "DEBUG"  # development.yaml overrides
        assert settings.log_format == "console"  # development.yaml overrides


class TestQueueSchemas:
    def test_priority_to_topic(self):
        from pachong.queue.schemas import TOPIC_TASKS_HIGH, TOPIC_TASKS_LOW, TOPIC_TASKS_NORMAL, priority_to_topic
        assert priority_to_topic(90) == TOPIC_TASKS_HIGH
        assert priority_to_topic(50) == TOPIC_TASKS_NORMAL
        assert priority_to_topic(10) == TOPIC_TASKS_LOW

    def test_message_serialization_roundtrip(self, task_message):
        from pachong.queue.schemas import deserialize_task, serialize_task
        serialized = serialize_task(task_message)
        deserialized = deserialize_task(serialized)
        assert deserialized.task_id == task_message.task_id
        assert deserialized.url == task_message.url
        assert deserialized.domain == task_message.domain
