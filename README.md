# PATH Arrivals Kiosk (Hoboken)

Windows-first PyQt6 display for live PATH arrivals from `ridepath.json`. Sized exactly for a 1920×720 stretched panel with big, clean text and minimal chrome.

## Setup (Windows 11)
- Install Python 3.11 (add to PATH).
- In this folder: `python -m venv .venv` then `.\.venv\Scripts\activate`.
- Install deps: `pip install -r requirements.txt`.
- Adjust `config.json` if desired (created automatically if missing).
- `start.bat` centralizes Python bytecode into `.pycache/` (sets `PYTHONPYCACHEPREFIX`) to keep the tree clean.

## Run
- `start.bat` launches the borderless 1920×720 window.
- Ctrl+Q exits (dev escape hatch).

## Config (`config.json`)
- `station`: station code (default `HOB`).
- Adaptive polling (with jitter ±10%):
  - `poll_baseline_seconds` (default 30)
  - `poll_aggressive_seconds` (<5 min soonest ETA, default 15)
  - `poll_relaxed_seconds` (>15 min soonest ETA, default 90)
  - `poll_background_seconds` (no messages, default 300)
  - `aggressive_threshold_seconds` (default 300)
  - `relaxed_threshold_seconds` (default 900)
  - `jitter_ratio` (default 0.1)
- Staleness:
  - `ttl_seconds` (default 45), `ttl_aggressive_seconds` (default 20)
  - `stale_no_change_polls` (unchanged payload polls to mark stale, default 3)
  - `stale_failure_polls` (failed polls to mark stale, default 3)
  - `stale_after_seconds` legacy fallback (default 120)
- `max_cards`: maximum cards shown on the left strip.
- `font_family`: preferred fonts, comma-separated.

## Behavior
- Polls `https://www.panynj.gov/bin/portauthority/ridepath.json` with a 5s timeout.
- Extracts only the entry where `consideredStation=="HOB"`; sorts by soonest `secondsToArrival`.
- Multi-color `lineColor` renders a split 50/50 bar.
- Right sidebar shows local clock, freshest `lastUpdated`, and a LIVE/STALE pill (stale if data is older than threshold, fetch failed, or messages are empty). On network failure it keeps last data but flips to STALE and retries with 5/10/20/.../60s backoff.
- Placeholder text appears when no messages are posted.
- Rotating log at `logs/app.log`.

## Tests
- Run parsing tests: `python -m pytest tests/test_path_data.py`.

## Optional: Single EXE
- Install PyInstaller (`pip install pyinstaller`).
- Build: `pyinstaller path_app.spec` (bundles defaults, PNG assets, and sets the EXE icon from `app-icon.png`). Copy `config.json` and `PATH_logo.png` next to the EXE if you change them.

## Kiosk-style autostart (Windows)
- Build the EXE (above) or use `start.bat` with Python installed.
- Register a Scheduled Task to start at logon (powershell as admin):
  `powershell -ExecutionPolicy Bypass -File scripts\register_kiosk_task.ps1 -AppPath "C:\path\to\path-kiosk.exe" -TaskName "PATHKiosk"`
  - To target a specific user: add `-User "MACHINE\\kioskuser"`.
- Set Windows auto-logon for the kiosk user (netplwiz or registry) so the device boots straight into the account and launches the task.
- Lock down power/sleep/screensaver and notifications to avoid interruptions.
- VS Code workspace: `path_app/path-app.code-workspace`.
