@echo off
title WhatsApp Monitor - Setup
echo.
echo =========================================
echo   WhatsApp Online Monitor - Setup
echo =========================================
echo.

echo [1/2] Installing Python dependencies...
python -m pip install playwright
if %errorlevel% neq 0 (
    echo ERROR: pip install failed. Make sure Python is installed and in PATH.
    pause
    exit /b 1
)

echo.
echo [2/2] Installing Playwright Chromium browser...
python -m playwright install chromium
if %errorlevel% neq 0 (
    echo ERROR: Playwright browser install failed.
    pause
    exit /b 1
)

echo.
echo =========================================
echo   Setup complete!
echo   Run the app with: run.bat
echo =========================================
echo.
pause
