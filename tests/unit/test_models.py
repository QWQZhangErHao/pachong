"""Unit tests for core Pydantic models."""

from __future__ import annotations

import uuid

from pachong.core.models import (
    BrowserIdentity,
    ProductRecord,
    ProxyRecord,
    ScrapingResult,
    ServerlessPayload,
    Task,
    TaskMessage,
    TaskStatus,
)


class TestTask:
    def test_task_creation_and_domain_auto_extract(self):
        task = Task(url="https://shop.example.com/product/123")
        assert task.domain == "shop.example.com"
        assert task.priority == 0  # default
        assert str(task.task_id)

    def test_task_domain_override(self):
        task = Task(url="https://other.com/item", domain="manual.domain.com")
        assert task.domain == "manual.domain.com"

    def test_task_priority_clamped(self):
        task = Task(url="https://x.com", priority=80)
        assert task.priority == 80

    def test_task_uuid_auto_generated(self):
        t1 = Task(url="https://x.com")
        t2 = Task(url="https://x.com")
        assert t1.task_id != t2.task_id


class TestBrowserIdentity:
    def test_identity_creation(self):
        identity = BrowserIdentity(
            name="test", timezone="Asia/Tokyo", locale="ja-JP"
        )
        assert identity.timezone == "Asia/Tokyo"
        assert identity.locale == "ja-JP"
        assert identity.screen_width == 1920  # default

    def test_identity_uuid(self):
        identity = BrowserIdentity(name="test")
        assert str(identity.identity_id)


class TestProxyRecord:
    def test_proxy_creation(self):
        proxy = ProxyRecord(host="10.0.0.1", port=3128)
        assert proxy.host == "10.0.0.1"
        assert proxy.port == 3128
        assert proxy.protocol.value == "http"


class TestServerlessPayload:
    def test_payload_is_compact(self):
        payload = ServerlessPayload(
            task_id=uuid.uuid4(),
            s3_bucket="bucket",
            s3_raw_html_key="raw/test.html",
        )
        json_str = payload.model_dump_json()
        assert len(json_str) < 300, f"Payload too large: {len(json_str)} bytes"

    def test_payload_no_dom_included(self):
        payload = ServerlessPayload(
            task_id=uuid.uuid4(),
            s3_bucket="bucket",
            s3_raw_html_key="raw/test.html",
        )
        json_str = payload.model_dump_json()
        assert "<html" not in json_str
        assert "DOM" not in json_str


class TestTaskStatus:
    def test_status_values(self):
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.QUEUED.value == "queued"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.SUCCESS.value == "success"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.DEFERRED.value == "deferred"
