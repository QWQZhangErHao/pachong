"""Configuration hierarchy using pydantic-settings with YAML support."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseModel):
    postgres_dsn: str = "postgresql+asyncpg://pachong:pachong@localhost:5432/pachong"
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db_name: str = "pachong"
    redis_uri: str = "redis://localhost:6379/0"
    postgres_pool_min: int = 5
    postgres_pool_max: int = 20
    mongo_pool_min: int = 5
    mongo_pool_max: int = 20
    redis_pool_size: int = 20


class S3Settings(BaseModel):
    endpoint: str = "http://localhost:9000"
    access_key: str = "minioadmin"
    secret_key: str = "minioadmin"
    bucket: str = "pachong-raw"
    region: str = "us-east-1"
    use_ssl: bool = False
    compression: Literal["brotli", "gzip"] = "brotli"
    compression_level: int = 6  # Brotli 0-11
    upload_timeout_ms: int = 60_000


class QueueSettings(BaseModel):
    backend: Literal["kafka", "rabbitmq"] = "kafka"
    kafka_brokers: list[str] = Field(default_factory=lambda: ["localhost:9092"])
    kafka_topic_prefix: str = "pachong"
    consumer_group: str = "pachong-workers"
    max_poll_records: int = 500
    session_timeout_ms: int = 30_000
    heartbeat_interval_ms: int = 3_000
    # Topic names derived from prefix:
    # {prefix}.tasks.high, {prefix}.tasks.normal, {prefix}.tasks.low
    # {prefix}.results, {prefix}.dead_letter


class NetworkSettings(BaseModel):
    max_concurrent_requests: int = 100
    connection_pool_size: int = 50
    http2_enabled: bool = True
    request_timeout_ms: int = 30_000
    connect_timeout_ms: int = 5_000
    dns_cache_ttl_seconds: int = 300
    tcp_keepalive_seconds: int = 60
    playwright_browser_count: int = 4
    playwright_headless: bool = True
    playwright_block_images: bool = True
    playwright_block_fonts: bool = True
    playwright_block_analytics: bool = True
    lightpanda_binary_path: str = "lightpanda"
    lightpanda_auto_restart: bool = True
    nodriver_max_concurrent: int = 2
    adaptive_decision_cache_ttl: int = 300  # 5 min
    adaptive_engine_scores: dict[str, float] = Field(
        default_factory=lambda: {"http": 1.0, "playwright": 0.8, "lightpanda": 0.95, "nodriver": 0.3}
    )


class AntiDetectSettings(BaseModel):
    identity_pool_size: int = 20
    identity_rotation_requests: int = 50
    fingerprint_consistency_check: bool = True
    geo_bound_enabled: bool = True
    geoip_db_path: str = "data/GeoLite2-City.mmdb"
    behavior_simulation_enabled: bool = False
    behavior_model_path: str = "data/behavior_model.pt"
    bandit_algorithm: Literal["thompson", "ucb", "exp3"] = "thompson"
    bandit_exploration_rate: float = 0.1
    proxy_pool_min_size: int = 20
    proxy_health_check_interval_ms: int = 60_000
    proxy_rotation_strategy: Literal["round_robin", "weighted", "bandit"] = "bandit"


class ExtractorSettings(BaseModel):
    default_strategy: Literal["schema_org", "css_xpath", "adaptive_ie", "multimodal"] = "css_xpath"
    rule_cache_ttl_seconds: int = 86_400  # 24h
    rule_max_retries: int = 3
    llm_healer_enabled: bool = True
    llm_healer_model: str = "gpt-4o"
    llm_healer_max_concurrent: int = 3
    redlock_ttl_ms: int = 30_000
    redlock_retry_count: int = 3
    redlock_retry_delay_ms: int = 500
    multimodal_model: str = "gpt-4o"
    multimodal_max_tokens: int = 4096
    render_service: Literal["splash", "lambda"] = "splash"
    render_service_url: str = "http://localhost:8050"
    render_timeout_ms: int = 15_000


class ResilienceSettings(BaseModel):
    ban_threshold_score: float = 0.5  # 0-1, above this = domain is in danger
    ban_detection_window_seconds: int = 300  # sliding window
    pid_kp: float = 0.5  # proportional gain
    pid_ki: float = 0.1  # integral gain
    pid_kd: float = 0.05  # derivative gain
    pid_target_block_rate: float = 0.05  # target 5%
    pid_update_interval_ms: int = 10_000
    circuit_breaker_failure_threshold: int = 10
    circuit_breaker_cooldown_seconds: int = 60
    circuit_breaker_half_open_max: int = 3
    default_domain_qps: float = 1.0  # safe default for unknown domains
    max_domain_qps: float = 10.0
    min_domain_qps: float = 0.1
    qps_backoff_multiplier: float = 0.5
    qps_recovery_multiplier: float = 1.2


class ServerlessSettings(BaseModel):
    enabled: bool = False
    provider: Literal["aws", "gcp", "local"] = "local"
    max_concurrent_functions: int = 50
    dispatch_queue_depth_threshold: int = 1000
    function_timeout_ms: int = 300_000  # 5 min
    function_memory_mb: int = 1024
    aws_lambda_function_name: str = "pachong-worker"
    gcp_function_name: str = "pachong-worker"


class TracingSettings(BaseModel):
    enabled: bool = True
    exporter: Literal["otlp", "console"] = "otlp"
    otlp_endpoint: str = "http://localhost:4317"
    service_name: str = "pachong"
    sample_rate: float = 1.0


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PACHONG_",
        env_nested_delimiter="__",
        case_sensitive=False,
    )

    env: str = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "json"

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    s3: S3Settings = Field(default_factory=S3Settings)
    queue: QueueSettings = Field(default_factory=QueueSettings)
    network: NetworkSettings = Field(default_factory=NetworkSettings)
    anti_detect: AntiDetectSettings = Field(default_factory=AntiDetectSettings)
    extractor: ExtractorSettings = Field(default_factory=ExtractorSettings)
    resilience: ResilienceSettings = Field(default_factory=ResilienceSettings)
    serverless: ServerlessSettings = Field(default_factory=ServerlessSettings)
    tracing: TracingSettings = Field(default_factory=TracingSettings)

    @classmethod
    def from_yaml(cls, yaml_path: str | Path) -> dict:
        """Read YAML file and return raw dict."""
        path = Path(yaml_path)
        if path.exists():
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
                return data or {}
        return {}

    def to_dict(self) -> dict:
        """Serialize settings to a nested dict."""
        import json
        return json.loads(self.model_dump_json())

    def merge_override(self, override: dict) -> "Settings":
        """Deep-merge an override dict and return new Settings instance."""
        base = self.to_dict()
        _deep_merge(base, override)
        return self.__class__(**base)

    @classmethod
    def load(cls, env: str | None = None) -> "Settings":
        """Load settings cascade: default.yaml → {env}.yaml → env vars."""
        config_dir = Path(__file__).parent.parent.parent / "config"

        # Layer 1: default.yaml
        merged = cls.from_yaml(config_dir / "default.yaml")

        # Determine env
        env = env or merged.get("env", "development")

        # Layer 2: environment-specific override
        env_data = cls.from_yaml(config_dir / f"{env}.yaml")
        _deep_merge(merged, env_data)

        # Layer 3: env vars handled by pydantic-settings BaseSettings
        return cls(**merged)


_global_settings: Settings | None = None
_config_mtime: float = 0.0


def get_settings() -> Settings:
    """Get current settings instance (cached, with hot-reload)."""
    global _global_settings, _config_mtime
    config_dir = Path(__file__).parent.parent.parent / "config"
    default_yaml = config_dir / "default.yaml"

    try:
        mtime = default_yaml.stat().st_mtime if default_yaml.exists() else 0
    except Exception:
        mtime = 0

    if _global_settings is None or mtime > _config_mtime:
        _global_settings = Settings.load()
        _config_mtime = mtime
    return _global_settings


def reload_config() -> Settings:
    """Force reload settings from YAML files (hot-reload)."""
    global _global_settings, _config_mtime
    _global_settings = Settings.load()
    _config_mtime = 0
    return _global_settings


def _deep_merge(base: dict, override: dict) -> None:
    """Recursively merge override into base (mutates base)."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
