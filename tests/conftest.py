"""Shared pytest fixtures for pachong tests."""

from __future__ import annotations

import pytest

from pachong.core.models import (
    BrowserIdentity,
    ProxyRecord,
    Task,
    TaskMessage,
)
from pachong.core.settings import Settings
from pachong.network.response import FetchResponse


@pytest.fixture
def settings() -> Settings:
    return Settings.load()


@pytest.fixture
def task() -> Task:
    return Task(url="https://example.com/product/test-123", priority=80)


@pytest.fixture
def task_message(task) -> TaskMessage:
    return TaskMessage(
        task_id=task.task_id,
        url=str(task.url),
        domain=task.domain,
        priority=task.priority,
    )


@pytest.fixture
def identity() -> BrowserIdentity:
    return BrowserIdentity(
        name="test-identity",
        timezone="America/New_York",
        locale="en-US",
        languages=["en-US", "en"],
        platform="Win32",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36",
        screen_width=1920,
        screen_height=1080,
    )


@pytest.fixture
def proxy_record() -> ProxyRecord:
    return ProxyRecord(
        host="192.168.1.1",
        port=8080,
        region="US",
        country="US",
        success_rate=0.95,
    )


@pytest.fixture
def fetch_response_ok() -> FetchResponse:
    resp = FetchResponse(
        url="https://example.com/product/test",
        status_code=200,
        content="<html><body>Test OK</body></html>",
    )
    resp.timing.total_ms = 500
    return resp


@pytest.fixture
def fetch_response_blocked() -> FetchResponse:
    return FetchResponse(
        url="https://example.com/product/test",
        status_code=503,
        is_js_challenge=True,
        js_challenge_type="cloudflare",
        content="<html><body>Just a moment...</body></html>",
    )


@pytest.fixture
def sample_html_product() -> str:
    return """<!DOCTYPE html><html><head>
<title>Test Product</title>
<meta property="og:title" content="Test Product">
<meta property="product:price:amount" content="29.99">
<meta property="product:price:currency" content="USD">
<meta property="og:image" content="https://img.example.com/test.jpg">
</head><body>
<h1>Test Product</h1>
<div class="price">$29.99</div>
<span itemprop="brand">TestBrand</span>
<span itemprop="availability" content="InStock">In Stock</span>
</body></html>"""


@pytest.fixture
def sample_html_jsonld() -> str:
    return """<!DOCTYPE html><html><head>
<script type="application/ld+json">
{"@type":"Product","name":"JSON-LD Product","sku":"JLD-001",
"offers":{"@type":"Offer","price":"49.99","priceCurrency":"EUR"},
"brand":{"@type":"Brand","name":"EuroBrand"},
"aggregateRating":{"ratingValue":"4.7","reviewCount":"256"}}
</script>
</head><body><h1>JSON-LD Product</h1></body></html>"""
