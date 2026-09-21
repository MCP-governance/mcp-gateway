@echo off
cd /d "%~dp0"
wsl -d kali-linux -- bash ./console.sh live-lab
if errorlevel 1 goto failed
start "" http://localhost:8000/
start "" http://localhost:8088/
echo Testbed ready. Keep this window open to keep Kali WSL and Docker running.
echo Run ./console.sh live-stop in WSL before closing it.
wsl -d kali-linux -- sleep infinity
exit /b 0
:failed
echo Setup failed. Check the message above, then run this file again.
pause
exit /b 1
