"""Abstract extractor interface and result types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExtractedField:
    """A single extracted field with metadata."""
    name: str
    value: Any
    selector_used: str | None = None
    confidence: float = 1.0  # 0.0-1.0
    source: str = "css_xpath"  # Which extractor produced this


@dataclass
class ExtractionResult:
    """Complete extraction result from one or more extractors."""
    url: str
    success: bool = False
    fields: list[ExtractedField] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    extractors_used: list[str] = field(default_factory=list)
    extraction_time_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for f in self.fields:
            result[f.name] = f.value
        return result

    def get(self, field_name: str) -> Any:
        for f in self.fields:
            if f.name == field_name:
                return f.value
        return None


class BaseExtractor(ABC):
    """Abstract base class for all extractors."""

    name: str = "base"

    @abstractmethod
    async def extract(self, html: str, url: str, **kwargs) -> ExtractionResult:
        """Extract structured data from HTML."""

    @property
    def is_available(self) -> bool:
        return True
