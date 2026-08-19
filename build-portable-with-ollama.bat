@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build-portable.ps1" -IncludeOllama
if errorlevel 1 pause
