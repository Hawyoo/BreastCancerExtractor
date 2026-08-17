@echo off
setlocal
cd /d "%~dp0"
docker compose restart
start "" "http://127.0.0.1:8765"

