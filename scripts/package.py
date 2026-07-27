#!/usr/bin/env python3
"""One-click packaging script for Pachong.

Creates a ready-to-distribute folder with:
- All source code
- All config files
- Bootstrap scripts (Windows .bat + cross-platform .sh)
- Installer script

Output: dist/pachong-portable/
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main():
    root = Path(__file__).parent
    dist = root / "dist" / "pachong-portable"
    if dist.exists():
        shutil.rmtree(dist)
    dist.mkdir(parents=True)

    print("=" * 55)
    print("  Pachong Portable Package Builder")
    print("=" * 55)
    print(f"\n  Output: {dist}")

    # === Copy source code ===
    print("\n[1/4] Copying source...")
    shutil.copytree(root / "pachong", dist / "pachong")
    shutil.copy(root / "pyproject.toml", dist / "pyproject.toml")

    # === Copy config files ===
    print("[2/4] Copying configs...")
    shutil.copytree(root / "config", dist / "config")

    # === Copy scripts ===
    print("[3/4] Copying entry scripts...")
    shutil.copy(root / "demo.py", dist / "demo.py")
    shutil.copy(root / "submit.py", dist / "submit.py")
    shutil.copy(root / "urls.txt", dist / "urls.txt")
    shutil.copy(root / "pachong.bat", dist / "pachong.bat")

    # === Write installer ===
    (dist / "install.bat").write_text("""@echo off
chcp 65001 >nul
echo ==========================================
echo   Pachong Installation
echo ==========================================
echo.
echo Installing pachong and dependencies...
pip install -e . -q
echo.
echo Done! Run with:
echo   pachong --help
echo.
echo Or use:
echo   pachong.bat run api      - Start API server
echo   pachong.bat run demo     - Run demo
echo   pachong.bat run submit FILE - Submit URLs
echo.
pause
""", encoding="utf-8")

    (dist / "README.txt").write_text("""Pachong v0.1.0 - Distributed E-Commerce Scraping System
=========================================================

Quick Start:
  Windows: 双击 pachong.bat 查看菜单
  或运行:  pachong.bat run demo

  Linux/Mac:
  $ python demo.py
  $ pachong --help

安装:
  Windows: 双击 install.bat
  或运行:  pip install -e .

提交任务:
  $ python submit.py --url "https://amazon.com/dp/B0TEST"

启动 API:
  $ pachong api
  $ open http://localhost:8000/docs

运行测试:
  $ python -m pytest tests/ -v
""", encoding="utf-8")

    # === Remove __pycache__ ===
    for pycache in dist.rglob("__pycache__"):
        shutil.rmtree(pycache)

    # === Zip for distribution ===
    print("[4/4] Creating archive...")
    zip_path = root / "dist" / "pachong-portable"
    shutil.make_archive(str(zip_path), "zip", root / "dist", "pachong-portable")

    zip_size_mb = (zip_path.with_suffix(".zip")).stat().st_size / (1024 * 1024)
    print(f"\n  Archive: {zip_path}.zip ({zip_size_mb:.1f} MB)")

    print(f"\n{'=' * 55}")
    print("  Package Complete!")
    print(f"{'=' * 55}")
    print(f"""
  Distribution methods:
  ┌───────────────────────────────────────────────────┐
  │ pip install pachong           (from dist/*.whl)  │
  │ dist/pachong-portable.zip     (portable, ~1MB)   │
  │ docker compose up -d          (full stack)        │
  │ python demo.py                (zero-install demo) │
  └───────────────────────────────────────────────────┘
""")


if __name__ == "__main__":
    main()
