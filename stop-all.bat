@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop-all.ps1"
set "STOP_EXIT=%ERRORLEVEL%"
if "%STOP_EXIT%"=="2" (
  echo.
  echo Full shutdown was cancelled.
  echo This window will close in 5 seconds.
  timeout /t 5 /nobreak >nul
  exit /b 0
)
if not "%STOP_EXIT%"=="0" (
  echo.
  echo Full shutdown did not complete. Exit code: %STOP_EXIT%
  echo This window will close in 5 seconds.
  timeout /t 5 /nobreak >nul
  exit /b %STOP_EXIT%
)
echo.
echo Docker Desktop and WSL have been shut down.
echo This window will close in 5 seconds.
timeout /t 5 /nobreak >nul
