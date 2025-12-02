# PATH Arrivals Kiosk (Hoboken)

Windows-first PyQt6 display for live PATH arrivals from `ridepath.json`. Sized exactly for a 1920×720 stretched panel with big, clean text and minimal chrome.

## Setup (Windows 11)
- Install Python 3.11 (add to PATH).
- In this folder: `python -m venv .venv` then `.\.venv\Scripts\activate`.
- Install deps: `pip install -r requirements.txt`.
- Adjust `config.json` if desired (created automatically if missing).

## Run
- `start.bat` launches the borderless 1920×720 window.
- Ctrl+Q exits (dev escape hatch).

## Config (`config.json`)
- `station`: station code (default `HOB`).
- `poll_seconds`: poll interval after a good fetch (default 45).
- `stale_after_seconds`: age threshold for marking STALE (default 120).
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
- Build: `pyinstaller path_app.spec` (bundles defaults and runs windowed/no-console).

