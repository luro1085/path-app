# PATH Arrivals Kiosk — Project Map for LLMs

Purpose: give an automated assistant a concise map of the codebase so it can tell a human how to set up and run the kiosk on another Windows machine.

## Setup on a new Windows machine
- Prereqs: Windows 11, Python 3.11, pip, and Git. Optional: PyInstaller if building an EXE.
- Clone and enter the repo, then create/activate a venv: `python -m venv .venv` then `.\.venv\Scripts\activate`.
- Install deps: `pip install -r requirements.txt`.
- First run: `start.bat` (or `python -m path_app`). `config.json` is created with defaults if missing.
- Adjust `config.json` to change station/polling/fonts. Logs write to `logs/app.log`.
- Run tests: `python -m pytest tests/test_path_data.py`.
- Build single-EXE (optional): `pip install pyinstaller` then `pyinstaller path_app.spec` (outputs to `dist/path-kiosk/`).
- Kiosk auto-start (optional): run `scripts\register_kiosk_task.ps1 -AppPath "<full path to exe or start.bat>" -TaskName "PATHKiosk" [-User "MACHINE\\user"]`.

## Directory and file map
- `path_app/` Python package for the kiosk UI and data handling.
  - `app.py` Main PyQt6 window: polls `ridepath.json`, handles backoff/jitter, renders arrival cards and status UI, writes rotating log to `logs/app.log`, supports `PATH_FAKE_FEED=1` for an embedded sample payload, and wires `config.json` into fonts/polling thresholds.
  - `config.py` Default config values and `load_config`, which writes `config.json` if absent and merges any overrides.
  - `path_data.py` Dataclasses and parsing helpers that normalize feed colors, arrival times, and timestamps; used by the UI and tests.
  - `__main__.py` Entry point for `python -m path_app`.
  - `__init__.py` Package marker.
  - `path-app.code-workspace` VS Code workspace pointing at the repo root.
- `scripts/`
  - `register_kiosk_task.ps1` Registers a Windows Scheduled Task to launch the EXE or `start.bat` at user logon (runs as the supplied user).
- `tests/`
  - `test_path_data.py` Unit tests covering feed parsing and color normalization.
- Top-level supporting files
  - `start.bat` Convenience launcher; pins `PYTHONPYCACHEPREFIX` to `.pycache/` and calls `python -m path_app`.
  - `requirements.txt` Runtime/dev dependencies (PyQt6, requests, pytest).
  - `config.json` Runtime settings (auto-generated from defaults; safe to edit).
  - `path_app.spec` PyInstaller spec bundling the app with icons/assets into `dist/path-kiosk/`.
  - Assets: `PATH_logo.png`, `Hoboken_logo-final_Teal_Round.png`, `app-icon.ico` (used in the UI and packaged EXE).
  - Git/runtime noise: `.gitignore`, `.pycache/`, `.pytest_cache/`, `build/` and `dist/` (PyInstaller outputs), `logs/` (runtime log file location).

## What to tell a user asking “how do I set this up?”
1. Install Python 3.11 and clone the repo.
2. Create/activate `.venv` and `pip install -r requirements.txt`.
3. Run `start.bat` (or `python -m path_app`) in the repo root; edit `config.json` if needed.
4. Optional: run tests with pytest; build an EXE with `pyinstaller path_app.spec`; register the scheduled task via the PowerShell script for kiosk mode.
