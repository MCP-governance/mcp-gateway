@echo off
setlocal
start "" powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0setup.ps1"
exit /b 0
