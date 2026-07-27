@echo off
chcp 65001 >nul
echo ============================================================
echo   Pachong - Build & Package
echo ============================================================
echo.
echo Choose build type:
echo   [1] pip installable package  (python -m build)
echo   [2] PyInstaller .exe          (standalone, no Python needed)
echo   [3] pip install in dev mode   (python -m pip install -e .)
echo   [4] Run all tests
echo   [5] Full release (wheel + exe)
echo.

set /p choice="Enter choice [1-5]: "

if "%choice%"=="1" goto pip_build
if "%choice%"=="2" goto exe_build
if "%choice%"=="3" goto dev_install
if "%choice%"=="4" goto run_tests
if "%choice%"=="5" goto full_release
echo Invalid choice
exit /b 1

:pip_build
echo.
echo === Building pip package ===
pip install build -q
python -m build
echo.
echo Output: dist\pachong-0.1.0-py3-none-any.whl
echo Install: pip install dist\pachong-0.1.0-py3-none-any.whl
goto end

:exe_build
echo.
echo === Building standalone .exe with PyInstaller ===
pip install pyinstaller -q
pyinstaller scripts/pachong.spec --clean
echo.
echo Output: dist\pachong.exe
echo Run:    dist\pachong.exe --help
goto end

:dev_install
echo.
echo === Installing in dev mode ===
pip install -e .
echo.
echo Run: pachong --help
goto end

:run_tests
echo.
echo === Running all tests ===
python -m pytest tests/ -v
goto end

:full_release
echo.
echo === Full Release Build ===
echo.
echo [1/3] Running tests...
python -m pytest tests/ -v -q
if %errorlevel% neq 0 (
    echo Tests failed! Aborting build.
    exit /b 1
)
echo.
echo [2/3] Building pip package...
pip install build -q
python -m build
echo.
echo [3/3] Building standalone .exe...
pip install pyinstaller -q
pyinstaller scripts/pachong.spec --clean
echo.
echo ============================================================
echo   Release Complete!
echo   - pip:    dist\pachong-0.1.0-py3-none-any.whl
echo   - exe:    dist\pachong.exe
echo ============================================================
goto end

:end
echo.
pause
