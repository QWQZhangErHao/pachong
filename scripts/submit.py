#!/usr/bin/env python3
"""Pachong task submission tool — submit URLs for crawling.

Usage:
    # Submit a single URL
    python submit.py --url "https://amazon.com/product/B00TEST"

    # Submit multiple URLs
    python submit.py --url "https://x.com/p/1" --url "https://x.com/p/2"

    # Submit with custom priority
    python submit.py --url "https://x.com/p/1" --priority 90

    # Submit URLs from a file (one per line)
    python submit.py --file urls.txt

    # Submit via HTTP API (when API server is running)
    python submit.py --url "https://x.com/p/1" --api http://localhost:8000

    # Auto-detect from clipboard (Windows)
    python submit.py --clipboard
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


async def submit_direct(urls: list[str], priority: int = 0, engine: str = "http") -> None:
    """Submit tasks directly to PostgreSQL (or in-memory fallback)."""
    from pachong.api.routes._task_service import create_task, _process_in_background

    print(f"\nSubmitting and processing {len(urls)} URL(s)...\n")
    print(f"{'Status':8s} {'Task ID':38s} {'Priority':>8s}  URL")
    print("-" * 90)

    tasks_created = []
    for url in urls:
        result = await create_task(url=url.strip(), priority=priority, engine_hint=engine)
        if result["status"] == "created":
            tasks_created.append(result)
        print(f"{'[OK]':8s} {result['task_id']:38s} {result['priority']:>8d}  {url}")

    # Process all tasks (sequentially for CLI, parallel via BackgroundTasks for API)
    for task in tasks_created:
        await _process_in_background(task["task_id"], task["url"], task["domain"])

    print(f"\nDone. {len(urls)} URL(s) submitted and processed.")


async def submit_via_api(urls: list[str], api_url: str, priority: int = 0) -> None:
    """Submit tasks via HTTP API."""
    import aiohttp

    api_url = api_url.rstrip("/")
    endpoint = f"{api_url}/api/tasks/submit/batch"

    payload = [
        {"url": url.strip(), "priority": priority} for url in urls
    ]

    async with aiohttp.ClientSession() as session:
        async with session.post(endpoint, json=payload) as resp:
            if resp.status == 200:
                data = await resp.json()
                print(f"Accepted: {data['accepted']}, Skipped: {data['skipped']}")
                for tid in data.get("task_ids", []):
                    print(f"  Task: {tid}")
            else:
                text = await resp.text()
                print(f"API error ({resp.status}): {text}")


async def main():
    parser = argparse.ArgumentParser(description="Pachong task submission tool")
    parser.add_argument("--url", action="append", dest="urls", help="URL to crawl (can be repeated)")
    parser.add_argument("--file", type=str, help="File containing URLs (one per line)")
    parser.add_argument("--priority", type=int, default=0, help="Priority 0-100 (0=auto)")
    parser.add_argument("--engine", type=str, default="http", choices=["http", "playwright", "lightpanda", "nodriver"])
    parser.add_argument("--api", type=str, help="Submit via HTTP API (e.g. http://localhost:8000)")
    parser.add_argument("--clipboard", action="store_true", help="Read URLs from clipboard")
    args = parser.parse_args()

    urls = list(args.urls or [])

    # Read from file
    if args.file:
        path = Path(args.file)
        if path.exists():
            urls.extend(path.read_text(encoding="utf-8").strip().splitlines())
        else:
            print(f"File not found: {args.file}")
            return

    # Read from clipboard
    if args.clipboard:
        try:
            import subprocess
            result = subprocess.run(["powershell", "-command", "Get-Clipboard"], capture_output=True, text=True)
            clipboard_text = result.stdout.strip()
            if clipboard_text:
                # Try to extract URLs from clipboard
                import re
                found = re.findall(r'https?://[^\s]+', clipboard_text)
                if found:
                    urls.extend(found)
                    print(f"Found {len(found)} URL(s) in clipboard")
                else:
                    urls.append(clipboard_text)
        except Exception:
            print("Failed to read clipboard")

    if not urls:
        parser.print_help()
        print("\nExample: python submit.py --url 'https://amazon.com/dp/B00TEST'")
        return

    # Deduplicate and clean
    urls = list(dict.fromkeys(u.strip() for u in urls if u.strip()))

    if args.api:
        await submit_via_api(urls, args.api, args.priority)
    else:
        await submit_direct(urls, args.priority, args.engine)


if __name__ == "__main__":
    asyncio.run(main())
