@echo off
rem 내 PC 연결 - 이 파일을 두 번 눌러 실행하고 권한 확인에 응하면 끝난다.
setlocal
cd /d "%~dp0"

net session >nul 2>&1
if errorlevel 1 (
  rem The one elevation: UAC. The elevated copy keeps this folder and reports who asked for it.
  rem One line, no caret continuation: this file is served from Linux and may arrive with LF endings.
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -Verb RunAs -FilePath '%~f0' -ArgumentList 'elevated',$env:USERNAME -WorkingDirectory '%~dp0'"
  exit /b 0
)

set "EMPLOYEE=%2"
if "%EMPLOYEE%"=="" set "EMPLOYEE=%USERNAME%"
set "PYTHON="
for /f "delims=" %%P in ('where py.exe 2^>nul') do set "PYTHON=%%P -3"
if not defined PYTHON for /f "delims=" %%P in ('where python.exe 2^>nul') do set "PYTHON=%%P"
if not defined PYTHON (
  echo Python 3.10 이상이 필요합니다. 모든 사용자용으로 설치한 뒤 다시 실행하세요.
  pause
  exit /b 2
)

%PYTHON% "%~dp0managed-windows.py" install --user "%EMPLOYEE%"
echo.
pause
