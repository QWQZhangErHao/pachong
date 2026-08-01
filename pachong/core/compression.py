"""Brotli/Gzip compression middleware for all S3-bound data."""

from __future__ import annotations

import gzip
from typing import Literal

import brotli

CompressionAlgo = Literal["brotli", "gzip"]


def compress(data: bytes, algo: CompressionAlgo = "brotli", level: int = 6) -> bytes:
    """Compress bytes with the chosen algorithm.

    Brotli quality range: 0-11 (6 is a good speed/ratio balance).
    """
    if algo == "brotli":
        return brotli.compress(data, quality=level)
    elif algo == "gzip":
        return gzip.compress(data, compresslevel=level)
    raise ValueError(f"Unknown compression algorithm: {algo}")


def decompress(data: bytes, algo: CompressionAlgo = "brotli") -> bytes:
    """Decompress bytes, auto-detecting Brotli vs Gzip."""
    if algo == "brotli":
        return brotli.decompress(data)
    elif algo == "gzip":
        return gzip.decompress(data)
    raise ValueError(f"Unknown compression algorithm: {algo}")


def compress_html(html: str, algo: CompressionAlgo = "brotli", level: int = 6) -> bytes:
    """Compress HTML string to bytes. HTML compresses extremely well (~85-90% reduction)."""
    return compress(html.encode("utf-8"), algo=algo, level=level)


def decompress_html(data: bytes, algo: CompressionAlgo = "brotli") -> str:
    """Decompress bytes back to HTML string."""
    return decompress(data, algo=algo).decode("utf-8")


def compression_ratio(original: bytes, compressed: bytes) -> float:
    """Return compression ratio as percentage (e.g., 85.0 means 85% smaller)."""
    if len(original) == 0:
        return 0.0
    return (1 - len(compressed) / len(original)) * 100
