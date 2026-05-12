"""Pydantic v2 models — single source of truth for all system entities."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator
from pydantic.types import UUID4


# ── Enums ────────────────────────────────────────────────────────────────────

class TaskStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    DEFERRED = "deferred"  # waiting for rate-limit token


class EngineType(str, Enum):
    HTTP = "http"
    PLAYWRIGHT = "playwright"
    LIGHTPANDA = "lightpanda"
    NODRIVER = "nodriver"


class ProxyProtocol(str, Enum):
    HTTP = "http"
    HTTPS = "https"
    SOCKS5 = "socks5"


class ProxyStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    BANNED = "banned"


class ExtractionStrategy(str, Enum):
    SCHEMA_ORG = "schema_org"
    CSS_XPATH = "css_xpath"
    ADAPTIVE_IE = "adaptive_ie"
    MULTIMODAL = "multimodal"


# ── Extraction Configuration ─────────────────────────────────────────────────

class ExtractionRule(BaseModel):
    """A cached extraction rule (XPath / CSS / JSONPath)."""
    rule_id: UUID4 = Field(default_factory=uuid.uuid4)
    domain: str
    path_pattern: str  # URL path pattern this rule applies to
    field_name: str
    selector_type: Literal["xpath", "css", "jsonpath", "regex"]
    selector: str
    attribute: str | None = None  # e.g., "content" for meta, "src" for img
    success_count: int = 0
    failure_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    ttl_seconds: int = 86400  # 24h default


class ExtractionConfig(BaseModel):
    strategy: ExtractionStrategy = ExtractionStrategy.CSS_XPATH
    rules: list[ExtractionRule] = Field(default_factory=list)
    target_schema: dict[str, Any] = Field(default_factory=dict)
    multimodal_enabled: bool = False
    fallback_strategies: list[ExtractionStrategy] = Field(default_factory=list)


# ── Core Entities ────────────────────────────────────────────────────────────

class Task(BaseModel):
    task_id: UUID4 = Field(default_factory=uuid.uuid4)
    url: HttpUrl
    method: Literal["GET", "POST"] = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    priority: int = Field(default=0, ge=0, le=100)
    domain: str = ""
    engine_hint: EngineType = EngineType.HTTP
    extractor_config: ExtractionConfig = Field(default_factory=ExtractionConfig)
    max_retries: int = 3
    timeout_ms: int = 30_000
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @model_validator(mode="after")
    def set_domain(self) -> "Task":
        if not self.domain and self.url:
            self.domain = self.url.host or ""
        return self


class BrowserIdentity(BaseModel):
    """Geo-Bound coherent browser identity — ALL fields internally consistent.

    Design principle: select proxy IP FIRST, then reverse-generate this identity
    based on the IP's real GeoIP location. Never randomize fields independently.
    """
    identity_id: UUID4 = Field(default_factory=uuid.uuid4)
    name: str = ""

    # Geo-bound fields (derived from proxy IP's GeoIP lookup)
    timezone: str = "America/New_York"  # IANA timezone
    locale: str = "en-US"
    languages: list[str] = Field(default_factory=lambda: ["en-US", "en"])
    ip_geolocation: tuple[float, float] | None = None  # (lat, lon)

    # Platform consistency group
    platform: Literal["Win32", "MacIntel", "Linux x86_64"] = "Win32"
    user_agent: str = ""
    oscpu: str = ""
    screen_width: int = 1920
    screen_height: int = 1080
    avail_width: int = 1920
    avail_height: int = 1040
    color_depth: int = 24
    pixel_depth: int = 24
    device_pixel_ratio: float = 1.0
    hardware_concurrency: int = 8
    device_memory: int = 8  # GB

    # Browser-specific
    browser_name: str = "Chrome"
    browser_version: str = "130.0.0.0"
    webkit_version: str = "537.36"

    # Canvas fingerprint
    canvas_winding: bool = True
    canvas_hash: str = ""
    canvas_image_data_url_seed: str = ""

    # WebGL fingerprint
    webgl_vendor: str = "Google Inc. (Intel)"
    webgl_renderer: str = "Intel Iris Xe Graphics"
    webgl_unmasked_vendor: str = "Intel"
    webgl_unmasked_renderer: str = "Intel Iris Xe Graphics"
    webgl_parameters: dict[str, Any] = Field(default_factory=dict)

    # Audio fingerprint
    audio_sample_rate: int = 44100
    audio_channel_count: int = 2
    audio_hash: str = ""

    # TLS fingerprint
    tls_ja3_hash: str = ""
    tls_ja4_hash: str = ""
    tls_cipher_suites: list[int] = Field(default_factory=list)
    tls_extensions: list[int] = Field(default_factory=list)
    http2_settings: dict[str, int] = Field(default_factory=dict)

    # Font set
    installed_fonts: list[str] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_used_at: datetime | None = None
    success_rate: float = 1.0
    ban_score: float = 0.0


class ProxyRecord(BaseModel):
    proxy_id: UUID4 = Field(default_factory=uuid.uuid4)
    protocol: ProxyProtocol = ProxyProtocol.HTTP
    host: str
    port: int
    username: str | None = None
    password: str | None = None
    region: str = "unknown"
    city: str | None = None
    country: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    isp: str | None = None
    asn: int | None = None
    success_rate: float = 1.0
    latency_p50_ms: float = 0.0
    latency_p99_ms: float = 0.0
    ban_score: float = 0.0
    consecutive_failures: int = 0
    last_checked: datetime = Field(default_factory=datetime.utcnow)
    status: ProxyStatus = ProxyStatus.ACTIVE
    tags: list[str] = Field(default_factory=list)


class ScrapingResult(BaseModel):
    result_id: UUID4 = Field(default_factory=uuid.uuid4)
    task_id: UUID4
    url: str
    status_code: int
    response_time_ms: float
    engine_used: str
    proxy_id: str | None = None
    identity_id: str | None = None
    extracted_data: dict[str, Any] = Field(default_factory=dict)
    s3_raw_key: str | None = None  # S3 key for raw HTML
    s3_screenshot_key: str | None = None  # S3 key for screenshot
    mongo_doc_id: str | None = None  # MongoDB document reference
    trace_id: str | None = None  # OpenTelemetry trace ID
    error_message: str | None = None
    retry_count: int = 0
    ban_indicators: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ProductRecord(BaseModel):
    """Structured product data extracted from e-commerce pages."""
    product_id: UUID4 = Field(default_factory=uuid.uuid4)
    result_id: UUID4
    source_url: str
    domain: str
    title: str = ""
    description: str = ""
    brand: str | None = None
    price: float | None = None
    currency: str = "USD"
    price_history: list[dict[str, Any]] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)
    category: str | None = None
    categories: list[str] = Field(default_factory=list)
    sku: str | None = None
    upc: str | None = None
    ean: str | None = None
    variants: list[dict[str, Any]] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
    ratings_count: int = 0
    ratings_average: float = 0.0
    reviews_count: int = 0
    in_stock: bool = True
    availability: str = ""
    raw_specs: dict[str, Any] = Field(default_factory=dict)
    extracted_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ── Message Schemas ──────────────────────────────────────────────────────────

class TaskMessage(BaseModel):
    """Wire format for Kafka task messages."""
    message_id: UUID4 = Field(default_factory=uuid.uuid4)
    task_id: UUID4
    url: str
    domain: str
    priority: int = 0
    engine_hint: str = "http"
    headers: dict[str, str] = Field(default_factory=dict)
    retry_count: int = 0
    max_retries: int = 3
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResultMessage(BaseModel):
    """Wire format for Kafka result messages."""
    message_id: UUID4 = Field(default_factory=uuid.uuid4)
    task_id: UUID4
    status: TaskStatus
    result_id: UUID4 | None = None
    error: str | None = None
    s3_raw_key: str | None = None
    mongo_doc_id: str | None = None
    trace_id: str | None = None
    processed_at: datetime = Field(default_factory=datetime.utcnow)


class ServerlessPayload(BaseModel):
    """Pointer-based payload for serverless functions — never send raw HTML."""
    task_id: UUID4
    s3_bucket: str
    s3_raw_html_key: str
    s3_screenshot_key: str | None = None
    extraction_rules: list[dict[str, Any]] = Field(default_factory=list)
    callback_topic: str = "pachong.results"


# ── Bandit / Identity Scoring ────────────────────────────────────────────────

class BanditArm(BaseModel):
    arm_id: str  # e.g., "proxy:{proxy_id}" or "identity:{identity_id}"
    arm_type: Literal["proxy", "identity"]
    trials: int = 0
    successes: int = 0
    failures: int = 0
    ban_hits: int = 0
    estimated_reward: float = 0.5
    last_used: datetime = Field(default_factory=datetime.utcnow)


class BanAlert(BaseModel):
    """Triggered when ban_detector identifies elevated risk for a domain."""
    domain: str
    ban_score: float  # 0.0 = safe, 1.0 = fully blocked
    trigger_reason: str
    current_qps: float
    recommended_qps: float
    active_proxies: int
    detected_at: datetime = Field(default_factory=datetime.utcnow)
