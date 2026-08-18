@echo off
setlocal
cd /d "%~dp0"
uv run --group native python -m app.native_launcher
if errorlevel 1 pause
