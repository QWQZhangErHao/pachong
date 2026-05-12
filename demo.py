#!/usr/bin/env python3
"""Pachong Zero-Dependency Demo - Full Crawl + Extraction Pipeline

Usage:
    python demo.py              # Run the demo
    python -m pytest tests/ -v  # Run all 51 tests
"""

import asyncio
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


SAMPLE_HTML = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>Apple AirPods Pro (2nd Gen) - JD.com</title>
<meta property="og:title" content="Apple AirPods Pro 2nd Gen ANC Wireless Earbuds">
<meta property="og:image" content="https://img.example.com/airpods-pro-2.jpg">
<meta property="product:price:amount" content="1799">
<meta property="product:price:currency" content="CNY">
<script type="application/ld+json">
{
  "@type": "Product",
  "name": "Apple AirPods Pro (2nd Gen) with MagSafe Charging Case",
  "sku": "10004578091234",
  "brand": {"@type": "Brand", "name": "Apple"},
  "offers": {
    "@type": "Offer",
    "price": "1799.00",
    "priceCurrency": "CNY",
    "availability": "InStock"
  },
  "aggregateRating": {
    "@type": "AggregateRating",
    "ratingValue": "4.8",
    "reviewCount": "528000"
  }
}
</script>
</head><body>
<h1>Apple AirPods Pro (2nd Gen) ANC Wireless Earbuds for iPhone/iPad/Mac</h1>
<div class="price"><span class="a-price"><span class="a-offscreen">$1,799.00</span></span></div>
<div class="breadcrumb"><a href="/">Home</a> &gt; <a href="/c/electronics">Electronics</a> &gt; <a href="/c/headphones">Headphones</a></div>
<span id="acrCustomerReviewText">528,000+ ratings</span>
<span id="bylineInfo">Apple</span>
<img id="landingImage" src="https://img.example.com/airpods-pro-main.jpg">
</body></html>"""


async def main():
    print("=" * 60)
    print("  Pachong - End-to-End E-Commerce Scraping Demo")
    print("=" * 60)

    # === Step 1: URL Priority Scoring ===
    from pachong.scheduler.priority import score_url, classify_url

    urls = [
        "https://amazon.cn/dp/B0CJ5YHZ7V",
        "https://shop.example.com/cart",
        "https://store.example.com/category/headphones",
        "https://mall.example.com/login",
    ]
    print("\n[Step 1] URL Priority Scoring")
    print("-" * 45)
    for u in urls:
        cls = classify_url(u)
        score = score_url(u)
        flag = "HIGH" if score >= 70 else "MED " if score >= 30 else "LOW "
        print(f"  [{flag}] [{cls:10s}] score={score:3d}  {u}")

    # === Step 2: Geo-Bound Browser Identity ===
    from pachong.anti_detect.identity.generator import IdentityGenerator

    gen = IdentityGenerator(seed=42)
    identity = gen.generate("Asia/Shanghai")

    print("\n[Step 2] Geo-Bound Browser Identity")
    print("-" * 45)
    print(f"  Timezone:   {identity.timezone}")
    print(f"  Language:   {identity.locale} ({', '.join(identity.languages)})")
    print(f"  Platform:   {identity.platform}")
    print(f"  Screen:     {identity.screen_width}x{identity.screen_height}")
    print(f"  GPU:        {identity.webgl_renderer}")
    print(f"  UA:         {identity.user_agent[:75]}...")

    # === Step 3: Multi-Layer Fingerprint ===
    from pachong.anti_detect.fingerprint.consistency import validate_identity
    from pachong.anti_detect.fingerprint.canvas import generate_canvas_hash
    from pachong.anti_detect.fingerprint.tls import build_tls_config
    from pachong.anti_detect.fingerprint.browser import get_sec_ch_ua_headers

    report = validate_identity(identity)
    canvas_hash = generate_canvas_hash(identity)
    tls_config = build_tls_config(identity)
    sec_ch = get_sec_ch_ua_headers(identity)

    print("\n[Step 3] Fingerprint Consistency Validation")
    print("-" * 45)
    print(f"  Canvas:      {canvas_hash[:16]}...")
    print(f"  JA3:         {tls_config['ja3_hash'][:16]}...")
    print(f"  JA4:         {tls_config['ja4_hash']}")
    print(f"  Sec-CH-UA:   {sec_ch['Sec-Ch-Ua-Platform']}")
    print(f"  Report:      {str(report)[:70]}")

    # === Step 4: Network Engine Simulation ===
    from pachong.network.response import FetchResponse

    print("\n[Step 4] Network Engine Simulation")
    print("-" * 45)
    engines = {"http": 234, "playwright": 1456, "lightpanda": 198, "nodriver": 3420}
    for engine, latency in engines.items():
        resp = FetchResponse(url="https://amazon.cn/dp/B0TEST", status_code=200, content="ok")
        resp.timing.total_ms = latency
        resp.engine_used = engine
        speed = "FAST" if latency < 500 else "SLOW" if latency > 2000 else "OK  "
        print(f"  [{speed}] {engine:12s} -> {latency:5.0f}ms  status={resp.status_code}")

    # === Step 5: Five-Tier Extraction Pipeline ===
    from pachong.core.settings import Settings
    from pachong.extractor.pipeline import ExtractionPipeline

    settings = Settings.load()
    pipeline = ExtractionPipeline(settings)

    print("\n[Step 5] Five-Tier Extraction Pipeline")
    print("-" * 45)

    result = await pipeline.extract(
        html=SAMPLE_HTML,
        url="https://amazon.cn/dp/B0CJ5YHZ7V",
        domain="amazon.cn",
    )

    print(f"  Success:    {result.success}")
    print(f"  Time:       {result.extraction_time_ms:.1f}ms")
    print(f"  Extractors: {', '.join(result.extractors_used)}")

    print()
    for label, key in [("Title", "title"), ("Price", "price"), ("Currency", "currency"),
                        ("Brand", "brand"), ("SKU", "sku"), ("Rating", "rating_value"),
                        ("Reviews", "review_count"), ("Image", "image"), ("Stock", "availability"),
                        ("Category", "category")]:
        val = result.get(key)
        if val is not None:
            print(f"  {label:12s} -> {val}")

    # === Step 6: Brotli Compression ===
    from pachong.core.compression import compress_html, compression_ratio

    compressed = compress_html(SAMPLE_HTML, "brotli")
    ratio = compression_ratio(SAMPLE_HTML.encode(), compressed)

    print(f"\n[Step 6] Brotli Compression (before S3 upload)")
    print("-" * 45)
    print(f"  Raw HTML:   {len(SAMPLE_HTML):,} bytes")
    print(f"  Compressed: {len(compressed):,} bytes")
    print(f"  Ratio:      {ratio:.1f}% reduction")

    # === Step 7: Anti-Bot Feedback Loop ===
    from pachong.anti_detect.bandit.feedback import compute_reward, compute_ban_indicator

    good = FetchResponse(url="https://x.com", status_code=200, content="ok")
    good.timing.total_ms = 500
    bad = FetchResponse(url="https://x.com", status_code=403, is_js_challenge=True, js_challenge_type="cloudflare")

    good_r = compute_reward(good, True)
    bad_r = compute_reward(bad, False)
    ban = compute_ban_indicator(bad)

    print(f"\n[Step 7] Anti-Bot Feedback + Bandit + PID")
    print("-" * 45)
    print(f"  Normal req:  reward={good_r:.2f} (keep using this proxy/identity)")
    print(f"  Blocked req: reward={bad_r:.2f} (bandit will deprioritize)")
    print(f"  Ban score:   {ban:.2f} -> PID reduces QPS for this domain")

    # === Summary ===
    print(f"\n{'=' * 60}")
    print("  Demo Complete - All 7 Steps Passed")
    print(f"{'=' * 60}")
    print()
    print("  [x] Priority Scoring    [x] Geo-Bound Identity")
    print("  [x] Fingerprint Suite   [x] Engine Selection")
    print("  [x] Extraction Pipeline [x] Brotli Compression")
    print("  [x] Bandit + PID Loop")
    print()
    print("  Run 'python -m pytest tests/ -v' for 51 unit/integration tests")


if __name__ == "__main__":
    asyncio.run(main())
