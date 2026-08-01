"""SQLAlchemy 2.0 async ORM models for PostgreSQL."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TaskModel(Base):
    __tablename__ = "tasks"

    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(10), default="GET")
    priority: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    engine_hint: Mapped[str] = mapped_column(String(20), default="http")
    extractor_config: Mapped[dict] = mapped_column(JSONB, default=dict)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    timeout_ms: Mapped[int] = mapped_column(Integer, default=30_000)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    results: Mapped[list[ResultModel]] = relationship(back_populates="task", cascade="all, delete-orphan")


class ResultModel(Base):
    __tablename__ = "results"

    result_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tasks.task_id"), index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    engine_used: Mapped[str | None] = mapped_column(String(20), nullable=True)
    proxy_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    identity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    s3_raw_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    s3_screenshot_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    mongo_doc_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    ban_indicators: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped[TaskModel] = relationship(back_populates="results")


class BrowserIdentityModel(Base):
    __tablename__ = "browser_identities"

    identity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    timezone: Mapped[str] = mapped_column(String(100))
    locale: Mapped[str] = mapped_column(String(10))
    languages: Mapped[list] = mapped_column(JSONB, default=list)
    platform: Mapped[str] = mapped_column(String(50))
    user_agent: Mapped[str] = mapped_column(Text)
    browser_name: Mapped[str] = mapped_column(String(50))
    browser_version: Mapped[str] = mapped_column(String(20))
    screen_width: Mapped[int] = mapped_column(Integer)
    screen_height: Mapped[int] = mapped_column(Integer)
    canvas_hash: Mapped[str] = mapped_column(String(64))
    webgl_vendor: Mapped[str] = mapped_column(String(255))
    webgl_renderer: Mapped[str] = mapped_column(String(255))
    audio_hash: Mapped[str] = mapped_column(String(64))
    tls_ja4_hash: Mapped[str] = mapped_column(String(64))
    success_rate: Mapped[float] = mapped_column(Float, default=1.0)
    ban_score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProxyModel(Base):
    __tablename__ = "proxies"

    proxy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    protocol: Mapped[str] = mapped_column(String(10))
    host: Mapped[str] = mapped_column(String(255), index=True)
    port: Mapped[int] = mapped_column(Integer)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password: Mapped[str | None] = mapped_column(Text, nullable=True)
    region: Mapped[str] = mapped_column(String(100))
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    isp: Mapped[str | None] = mapped_column(String(255), nullable=True)
    asn: Mapped[int | None] = mapped_column(Integer, nullable=True)
    success_rate: Mapped[float] = mapped_column(Float, default=1.0)
    latency_p50_ms: Mapped[float] = mapped_column(Float, default=0.0)
    latency_p99_ms: Mapped[float] = mapped_column(Float, default=0.0)
    ban_score: Mapped[float] = mapped_column(Float, default=0.0)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="active")
    last_checked: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DomainBanState(Base):
    """Per-domain ban detection state for PID controller input."""
    __tablename__ = "domain_ban_states"

    domain: Mapped[str] = mapped_column(String(255), primary_key=True)
    total_requests: Mapped[int] = mapped_column(Integer, default=0)
    blocked_requests: Mapped[int] = mapped_column(Integer, default=0)
    captcha_requests: Mapped[int] = mapped_column(Integer, default=0)
    blank_page_requests: Mapped[int] = mapped_column(Integer, default=0)
    current_ban_score: Mapped[float] = mapped_column(Float, default=0.0)
    current_allowed_qps: Mapped[float] = mapped_column(Float, default=1.0)
    pid_p_term: Mapped[float] = mapped_column(Float, default=0.0)
    pid_i_term: Mapped[float] = mapped_column(Float, default=0.0)
    pid_d_term: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ExtractionRuleModel(Base):
    """Cached extraction rules persisted to Postgres as source of truth."""
    __tablename__ = "extraction_rules"

    rule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    path_pattern: Mapped[str] = mapped_column(Text, nullable=False)
    field_name: Mapped[str] = mapped_column(String(255), nullable=False)
    selector_type: Mapped[str] = mapped_column(String(20), nullable=False)
    selector: Mapped[str] = mapped_column(Text, nullable=False)
    attribute: Mapped[str | None] = mapped_column(String(100), nullable=True)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
