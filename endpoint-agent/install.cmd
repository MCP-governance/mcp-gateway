@echo off
setlocal
set "MCPGW_SETUP=%~dp0setup.ps1"
rem A hidden start keeps the wizard out of a terminal window; "start" would open one for the whole wizard.
powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -Command "Start-Process -FilePath (Join-Path $PSHOME 'powershell.exe') -WindowStyle Hidden -ArgumentList ('-NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File \"' + $env:MCPGW_SETUP + '\"')"
exit /b 0
