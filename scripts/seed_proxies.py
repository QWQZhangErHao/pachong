#!/usr/bin/env python3
"""Seed the proxy pool with sample proxies for development/testing."""

from __future__ import annotations

import asyncio

from pachong.anti_detect.proxy.pool import add_proxy
from pachong.core.models import ProxyProtocol, ProxyRecord
from pachong.storage.redis_.client import init_redis
from pachong.core.settings import Settings

SAMPLE_PROXIES = [
    {"host": "us-proxy-1.example.com", "port": 8080, "region": "US", "country": "US", "city": "New York", "lat": 40.71, "lon": -74.00},
    {"host": "us-proxy-2.example.com", "port": 8080, "region": "US", "country": "US", "city": "San Francisco", "lat": 37.77, "lon": -122.41},
    {"host": "eu-proxy-1.example.com", "port": 8080, "region": "EU", "country": "DE", "city": "Berlin", "lat": 52.52, "lon": 13.40},
    {"host": "eu-proxy-2.example.com", "port": 8080, "region": "EU", "country": "FR", "city": "Paris", "lat": 48.85, "lon": 2.35},
    {"host": "uk-proxy-1.example.com", "port": 8080, "region": "EU", "country": "GB", "city": "London", "lat": 51.50, "lon": -0.12},
    {"host": "jp-proxy-1.example.com", "port": 8080, "region": "AS", "country": "JP", "city": "Tokyo", "lat": 35.67, "lon": 139.76},
    {"host": "sg-proxy-1.example.com", "port": 8080, "region": "AS", "country": "SG", "city": "Singapore", "lat": 1.35, "lon": 103.81},
    {"host": "ca-proxy-1.example.com", "port": 8080, "region": "NA", "country": "CA", "city": "Toronto", "lat": 43.65, "lon": -79.38},
    {"host": "au-proxy-1.example.com", "port": 8080, "region": "OC", "country": "AU", "city": "Sydney", "lat": -33.86, "lon": 151.20},
    {"host": "br-proxy-1.example.com", "port": 8080, "region": "SA", "country": "BR", "city": "Sao Paulo", "lat": -23.55, "lon": -46.63},
]


async def main():
    settings = Settings.load()
    init_redis(settings)
    print(f"Seeding {len(SAMPLE_PROXIES)} sample proxies...")

    for p in SAMPLE_PROXIES:
        proxy = ProxyRecord(
            host=p["host"],
            port=p["port"],
            region=p["region"],
            country=p["country"],
            city=p["city"],
            latitude=p["lat"],
            longitude=p["lon"],
        )
        pid = await add_proxy(proxy)
        print(f"  Added: {p['host']} ({p['region']}) -> {pid}")

    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
