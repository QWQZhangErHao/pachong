@echo off
chcp 65001 >nul
title Pachong

if "%1"=="" (
    echo ========================================================
    echo   Pachong v0.1.0 - Distributed E-Commerce Scraping
    echo ========================================================
    echo.
    echo Commands:
    echo   run api           Start API server on http://localhost:8000
    echo   run demo          Run end-to-end demo
    echo   run test          Run all 51 tests
    echo   run submit FILE   Submit URLs from file
    echo   run shell         Open Python shell with pachong loaded
    echo.
    echo Examples:
    echo   pachong.bat run api
    echo   pachong.bat run demo
    echo   pachong.bat run submit urls.txt
    echo.
    goto :end
)

if "%1"=="run" (
    if "%2"=="api" (
        echo Starting Pachong API on http://localhost:8000 ...
        python -m uvicorn pachong.api.app:app --host 0.0.0.0 --port 8000
    ) else if "%2"=="demo" (
        python demo.py
    ) else if "%2"=="test" (
        python -m pytest tests/ -v
    ) else if "%2"=="submit" (
        python scripts/submit.py --file "%3"
    ) else if "%2"=="shell" (
        python -c "import pachong; from pachong.core.settings import Settings; from pachong.core.models import *; from pachong.anti_detect.identity.generator import IdentityGenerator; from pachong.extractor.pipeline import ExtractionPipeline; print('Pachong shell ready. Try: IdentityGenerator().generate(\"Asia/Shanghai\")')" && python
    ) else (
        echo Unknown command: %2
    )
    goto :end
)

echo Unknown option: %1
echo Use: pachong.bat run [api^|demo^|test^|submit^|shell]

:end