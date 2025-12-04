@echo off
cd /d "%~dp0"
set PYTHONPYCACHEPREFIX=%~dp0.pycache
python -m path_app
