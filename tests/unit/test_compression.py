"""Unit tests for Brotli/Gzip compression."""

from __future__ import annotations

from pachong.core.compression import (
    compress,
    compress_html,
    compression_ratio,
    decompress_html,
)


class TestCompression:
    def test_brotli_roundtrip(self):
        html = "<html><body>" + "Hello World " * 100 + "</body></html>"
        compressed = compress_html(html, "brotli")
        assert len(compressed) < len(html) * 0.3  # At least 70% compression
        decompressed = decompress_html(compressed, "brotli")
        assert decompressed == html

    def test_gzip_roundtrip(self):
        html = "<html><body>" + "Hello World " * 100 + "</body></html>"
        compressed = compress_html(html, "gzip")
        decompressed = decompress_html(compressed, "gzip")
        assert decompressed == html

    def test_compression_ratio(self):
        data = b"AAAA" * 100  # Highly compressible
        compressed = compress(data, "brotli", level=6)
        ratio = compression_ratio(data, compressed)
        assert ratio > 85  # Very high ratio for repetitive data

    def test_empty_ratio(self):
        assert compression_ratio(b"", b"") == 0.0

    def test_large_html_compression(self):
        """Large HTML should compress extremely well (~90%+ reduction)."""
        html = "<!DOCTYPE html><html><head></head><body>" + "<p>test paragraph</p>" * 500 + "</body></html>"
        compressed = compress_html(html, "brotli")
        ratio = compression_ratio(html.encode(), compressed)
        assert ratio > 90, f"Expected >90% compression, got {ratio:.1f}%"
