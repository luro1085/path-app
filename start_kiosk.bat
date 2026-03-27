@echo off
cd /d %~dp0
set PYTHONPYCACHEPREFIX=%~dp0.pycache

:loop
echo [%date% %time%] Starting PATH app... >> logs\kiosk.log
"%~dp0.venv\Scripts\python.exe" -m path_app
echo [%date% %time%] App exited with code %ERRORLEVEL% >> logs\kiosk.log

REM Clean up stale Chromium caches that accumulate over time
if exist "%LOCALAPPDATA%\path-app\QtWebEngine\Default\Cache" (
    rd /s /q "%LOCALAPPDATA%\path-app\QtWebEngine\Default\Cache" 2>nul
)

REM Wait 5 seconds before restarting to avoid tight crash loops
timeout /t 5 /nobreak >nul
goto loop
