"""Type aliases used throughout the system."""

from __future__ import annotations

from typing import Any, TypeAlias

# Domain name (e.g., "amazon.com")
Domain: TypeAlias = str

# URL pattern for sitemap matching (e.g., "/products/{sku}")
UrlPattern: TypeAlias = str

# JSON-serializable data from extraction
ExtractedJSON: TypeAlias = dict[str, Any]

# Kafka partition key
PartitionKey: TypeAlias = bytes

# S3 object key
S3Key: TypeAlias = str

# Prometheus label dict
MetricLabels: TypeAlias = dict[str, str]
