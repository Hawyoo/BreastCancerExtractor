@echo off
setlocal
cd /d "%~dp0"
where docker >nul 2>nul || (
  echo Docker Desktop is not installed or is not running.
  pause
  exit /b 1
)
docker compose up -d --build || (
  echo Failed to start Breast Cancer Extractor.
  pause
  exit /b 1
)
start "" "http://127.0.0.1:8765"
echo Breast Cancer Extractor started at http://127.0.0.1:8765

