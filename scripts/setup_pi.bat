@echo off
REM Edini Pi setup script for Windows
REM Ensures Pi is installed and extensions are configured

echo === Edini Pi Setup ===

REM Check if pi is installed
where pi >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Installing Pi coding agent...
    npm install -g @earendil-works/pi-coding-agent
) else (
    echo Pi is already installed:
    pi --version
)

REM Verify extensions directory exists
if not exist "%~dp0..\pi-extensions" (
    echo ERROR: pi-extensions directory not found
    exit /b 1
)

echo Setup complete. Run Edini from Houdini.
