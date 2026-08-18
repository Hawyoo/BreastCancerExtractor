@echo off
setlocal
cd /d "%~dp0"

echo Breast Cancer Extractor - automatic setup
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1"
set "INSTALL_EXIT=%ERRORLEVEL%"

if not "%INSTALL_EXIT%"=="0" (
  echo.
  echo Setup did not complete. Exit code: %INSTALL_EXIT%
  echo Follow the message above, then run install.bat again.
  echo This window will close in 5 seconds.
  timeout /t 5 /nobreak >nul
  exit /b %INSTALL_EXIT%
)

echo.
echo Setup and startup completed.
echo This window will close in 5 seconds.
timeout /t 5 /nobreak >nul
