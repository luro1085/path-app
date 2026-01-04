@echo off
cd /d %~dp0
set PYTHONPYCACHEPREFIX=%~dp0.pycache
"%~dp0.venv\Scripts\python.exe" -m path_app
