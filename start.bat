@echo off
chcp 65001 >nul
title Pachong Console
echo ===========================================
echo   Pachong - E-Commerce Scraping System
echo ===========================================
echo.
echo Starting server on http://localhost:8000 ...
echo Opening browser in 2 seconds...
echo.
echo Press Ctrl+C to stop the server.
echo ===========================================

:: Use PowerShell to open the default browser after a short delay
start /b powershell -command "Start-Sleep 2; Start-Process 'http://localhost:8000'"

:: Start the API server (serves GUI + API)
python -m uvicorn pachong.api.app:app --host 0.0.0.0 --port 8000
