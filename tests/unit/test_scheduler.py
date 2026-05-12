"""Unit tests for scheduler priority and URL classification."""

from __future__ import annotations

from pachong.scheduler.priority import classify_url, score_url


class TestPriorityScoring:
    def test_product_pages_score_high(self):
        assert score_url("https://amazon.com/product/test") >= 85
        assert score_url("https://shop.com/dp/B00TEST") >= 85
        assert score_url("https://store.com/item/12345") >= 85

    def test_low_value_pages_score_low(self):
        assert score_url("https://shop.com/cart") <= 10
        assert score_url("https://shop.com/login") <= 10
        assert score_url("https://shop.com/checkout") <= 10

    def test_category_pages_score_mid(self):
        score = score_url("https://shop.com/category/electronics")
        assert 50 <= score <= 85

    def test_domain_value_bonus(self):
        amazon_score = score_url("https://amazon.com/product/test")
        unknown_score = score_url("https://unknownshop.com/product/test")
        assert amazon_score >= unknown_score

    def test_score_range(self):
        """All scores must be in 0-100 range."""
        urls = [
            "https://amazon.com/product/test",
            "https://shop.com/cart",
            "https://shop.com/category/electronics",
            "https://shop.com/about",
        ]
        for url in urls:
            s = score_url(url)
            assert 0 <= s <= 100, f"Score {s} out of range for {url}"


class TestURLClassification:
    def test_product_classification(self):
        assert classify_url("https://x.com/product/123") == "product"
        assert classify_url("https://x.com/dp/B00TEST") == "product"
        assert classify_url("https://x.com/item/abc") == "product"
        assert classify_url("https://x.com/gp/product/X") == "product"

    def test_category_classification(self):
        assert classify_url("https://x.com/category/electronics") == "category"
        assert classify_url("https://x.com/search?q=test") == "category"

    def test_low_value_classification(self):
        assert classify_url("https://x.com/login") == "low_value"
        assert classify_url("https://x.com/cart") == "low_value"
        assert classify_url("https://x.com/account") == "low_value"

    def test_unknown_classification(self):
        assert classify_url("https://x.com/random-page") == "unknown"
