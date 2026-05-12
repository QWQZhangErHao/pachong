"""Integration tests for the adaptive engine selector and middleware."""

from __future__ import annotations

import asyncio

from pachong.core.settings import Settings
from pachong.network.adaptive import AdaptiveEngineSelector
from pachong.network.middleware import (
    MiddlewarePipeline,
    cookie_middleware,
    header_middleware,
    retry_middleware,
    timing_middleware,
)
from pachong.network.response import FetchResponse, TimingInfo


class TestAdaptiveEngine:
    def test_engine_order_default(self):
        settings = Settings.load()
        selector = AdaptiveEngineSelector(settings.network)
        order = selector._build_engine_order(None)
        assert order == ["http", "playwright", "lightpanda", "nodriver"]

    def test_engine_order_with_cached_playwright(self):
        settings = Settings.load()
        selector = AdaptiveEngineSelector(settings.network)
        order = selector._build_engine_order("playwright")
        assert order[0] == "playwright"
        assert "http" in order  # Still available as fallback


class TestMiddlewarePipeline:
    def test_default_pipeline_builds(self):
        pipeline = MiddlewarePipeline.default(max_retries=2)
        assert pipeline is not None
        assert len(pipeline._middlewares) == 2  # retry + timing

    def test_custom_pipeline(self):
        from pachong.core.models import BrowserIdentity

        identity = BrowserIdentity(
            user_agent="TestAgent/1.0", locale="de-DE"
        )
        pipeline = MiddlewarePipeline()
        pipeline.add(retry_middleware(2))
        pipeline.add(timing_middleware())
        pipeline.add(header_middleware(identity))
        assert len(pipeline._middlewares) == 3

    def test_build_wraps_handler(self):
        async def handler(**kw):
            return FetchResponse(url=kw.get("url", ""), status_code=200, content="ok")

        pipeline = MiddlewarePipeline.default(max_retries=1)
        wrapped = pipeline.build(handler)

        response = asyncio.run(wrapped(url="https://example.com"))
        assert response.is_success
        assert response.retry_count == 0


class TestRetryMiddleware:
    def test_retries_on_exception(self):
        call_count = [0]

        async def failing_handler(**kw):
            call_count[0] += 1
            if call_count[0] < 3:
                raise OSError("connection reset")
            return FetchResponse(url="https://x.com", status_code=200, content="ok")

        wrapped = retry_middleware(max_retries=3)(failing_handler)
        response = asyncio.run(wrapped(url="https://x.com"))
        assert response.is_success
        assert call_count[0] == 3
        assert response.retry_count == 2  # 0-indexed

    def test_gives_up_after_max_retries(self):
        async def always_fails(**kw):
            raise OSError("connection refused")

        wrapped = retry_middleware(max_retries=2)(always_fails)
        response = asyncio.run(wrapped(url="https://x.com"))
        assert not response.is_success
        assert response.retry_count == 2
