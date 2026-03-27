from __future__ import annotations

import json
import logging
import sys
import threading
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional
import random
import os

import requests
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtWebEngineWidgets import QWebEngineView  # type: ignore[import-untyped]
from PyQt6.QtWebEngineCore import QWebEngineSettings  # type: ignore[import-untyped]

from .board_format import build_board_rows, has_delayed_visible_trains
from .config import AppConfig, load_config
from .path_data import (
    STATION_DISPLAY_NAMES,
    StationData,
    is_presumed_service_active,
    parse_station_data_with_presumed,
)

LOG_PATH = Path("logs/app.log")
FEED_URL = "https://www.panynj.gov/bin/portauthority/ridepath.json"
ICON_PATH = Path("app-icon.ico") if Path("app-icon.ico").exists() else Path("app-icon.png")

# Optional hardcoded test payload: set PATH_FAKE_FEED=1 to use this instead of live feed
FAKE_PAYLOAD_HOB = {
    "consideredStation": "HOB",
    "destinations": [
        {
            "label": "ToNJ",
            "messages": [
                {
                    "target": "JSQ",
                    "secondsToArrival": "34",
                    "arrivalTimeMessage": "Delayed",
                    "lineColor": "4D92FB,FF9900",
                    "headSign": "Journal Square via Hoboken",
                    "lastUpdated": "2025-10-08T01:45:06.270303-04:00",
                },
                {
                    "target": "JSQ",
                    "secondsToArrival": "2260",
                    "arrivalTimeMessage": "38 min",
                    "lineColor": "4D92FB,FF9900",
                    "headSign": "Journal Square via Hoboken",
                    "lastUpdated": "2025-10-08T01:45:06.270303-04:00",
                },
                {
                    "target": "JSQ",
                    "secondsToArrival": "3000",
                    "arrivalTimeMessage": "50 min",
                    "lineColor": "4D92FB,FF9900",
                    "headSign": "Journal Square via Hoboken",
                    "lastUpdated": "2025-10-08T01:45:06.270303-04:00",
                }
            ],
        },
        {
            "label": "ToNY",
            "messages": [
                {
                    "target": "33S",
                    "secondsToArrival": "39",
                    "arrivalTimeMessage": "1 min",
                    "lineColor": "4D92FB,FF9900",
                    "headSign": "33rd Street via Hoboken",
                    "lastUpdated": "2025-10-08T01:45:06.270303-04:00",
                },
                {
                    "target": "33S",
                    "secondsToArrival": "2139",
                    "arrivalTimeMessage": "36 min",
                    "lineColor": "4D92FB,FF9900",
                    "headSign": "33rd Street via Hoboken",
                    "lastUpdated": "2025-10-08T01:45:06.270303-04:00",
                },
                {
                    "target": "33S",
                    "secondsToArrival": "3000",
                    "arrivalTimeMessage": "50 min",
                    "lineColor": "4D92FB,FF9900",
                    "headSign": "33rd Street via Hoboken",
                    "lastUpdated": "2025-10-08T01:45:06.270303-04:00",
                }
            ],
        },
    ],
}
FAKE_PAYLOAD_CHR = {
    "consideredStation": "CHR",
    "destinations": [
        {
            "label": "ToNJ",
            "messages": [
                {
                    "target": "JSQ",
                    "secondsToArrival": "600",
                    "arrivalTimeMessage": "10 min",
                    "lineColor": "4D92FB,FF9900",
                    "headSign": "Journal Square via Hoboken",
                    "lastUpdated": "2025-10-08T01:45:06.270303-04:00",
                }
            ],
        }
    ],
}


def setup_logging() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(LOG_PATH, maxBytes=512_000, backupCount=3)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=[handler])


class FetchThread(QtCore.QThread):
    data_received = QtCore.pyqtSignal(object)
    fetch_failed = QtCore.pyqtSignal(str)

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config
        self.session = requests.Session()
        self._stop_event = threading.Event()
        self._backoff_seconds = 5

    def run(self) -> None:
        delay = 0
        while not self._stop_event.is_set():
            if delay:
                if self._stop_event.wait(delay):
                    break
            try:
                station_data = self._fetch_once()
                self.data_received.emit(station_data)
                self._backoff_seconds = self.config.poll_baseline_seconds
                delay = self._next_delay(station_data)
            except Exception as exc:  # pragma: no cover - network issues
                logging.warning("Fetch failed: %s", exc)
                self.fetch_failed.emit(str(exc))
                if self._backoff_seconds < 5:
                    self._backoff_seconds = 5
                delay = min(60, self._backoff_seconds)
                self._backoff_seconds = min(60, self._backoff_seconds * 2)
        self.session.close()

    def stop(self) -> None:
        self._stop_event.set()

    def _fetch_once(self) -> StationData:
        include_presumed = self.config.show_presumed_trains and is_presumed_service_active(datetime.now())
        if os.getenv("PATH_FAKE_FEED"):
            payload = {"results": [FAKE_PAYLOAD_HOB, FAKE_PAYLOAD_CHR]}
            return parse_station_data_with_presumed(
                payload,
                self.config.station,
                include_presumed=include_presumed,
            )
        resp = self.session.get(FEED_URL, timeout=5)
        resp.raise_for_status()
        return parse_station_data_with_presumed(
            resp.json(),
            self.config.station,
            include_presumed=include_presumed,
        )

    def _next_delay(self, data: StationData) -> float:
        """Adaptive polling interval with jitter."""
        if not data.messages:
            base = self.config.poll_background_seconds
        else:
            soonest = min(msg.seconds_to_arrival for msg in data.messages)
            if soonest < self.config.aggressive_threshold_seconds:
                base = self.config.poll_aggressive_seconds
            elif soonest > self.config.relaxed_threshold_seconds:
                base = self.config.poll_relaxed_seconds
            else:
                base = self.config.poll_baseline_seconds
        jitter = 1 + random.uniform(-self.config.jitter_ratio, self.config.jitter_ratio)
        return max(5, base * jitter)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, config: AppConfig):
        super().__init__()
        self.config = config
        self.latest_data: Optional[StationData] = None
        self.last_fetch_ok = False
        self.last_successful_fetch: Optional[datetime] = None
        self.last_signature: Optional[tuple] = None
        self.unchanged_polls: int = 0
        self.consecutive_failures: int = 0
        self._page_ready = False
        self._pending_update = False

        self.setWindowTitle("PATH Arrivals - Hoboken")
        if ICON_PATH.exists():
            self.setWindowIcon(QtGui.QIcon(str(ICON_PATH)))
        self.setWindowFlag(QtCore.Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(QtCore.Qt.WindowType.WindowStaysOnTopHint, True)
        self.setFixedSize(1920, 720)
        self.setStyleSheet("background-color: #111;")
        self.move(0, 0)

        self._build_ui()

        self.fetch_thread = FetchThread(self.config)
        self.fetch_thread.data_received.connect(self.on_data_received)
        self.fetch_thread.fetch_failed.connect(self.on_fetch_failed)
        self.fetch_thread.start()

        # Periodic staleness check — re-evaluate every second like the old app
        self._staleness_timer = QtCore.QTimer(self)
        self._staleness_timer.setInterval(1000)
        self._staleness_timer.timeout.connect(self._send_status)
        self._staleness_timer.start()

    def _build_ui(self) -> None:
        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        self.web_view = QWebEngineView()
        self.web_view.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.NoContextMenu)

        # Allow audio autoplay (no user gesture needed in kiosk)
        settings = self.web_view.page().settings()
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False
        )

        self.web_view.loadFinished.connect(self._on_page_loaded)

        # Resolve path to web/index.html
        if getattr(sys, "frozen", False):
            base_path = Path(sys._MEIPASS)
        else:
            base_path = Path(__file__).parent
        web_path = base_path / "web" / "index.html"
        self.web_view.setUrl(QtCore.QUrl.fromLocalFile(str(web_path)))

        layout.addWidget(self.web_view)
        self.setCentralWidget(central)

    def _on_page_loaded(self, ok: bool) -> None:
        if not ok:
            logging.error("Failed to load web UI")
            return
        self._page_ready = True

        # Set station name
        station_name = STATION_DISPLAY_NAMES.get(
            self.config.station, self.config.station
        )
        self._run_js(f"setStation({json.dumps(station_name)})")

        # Send initial status
        self._send_status()

        # If data arrived before page loaded, send it now
        if self._pending_update:
            self._pending_update = False
            self.refresh_board()

    def _run_js(self, code: str) -> None:
        if self._page_ready:
            self.web_view.page().runJavaScript(code)

    def on_data_received(self, data: StationData) -> None:
        self.latest_data = data
        self.last_fetch_ok = True
        self.consecutive_failures = 0

        signature = self._build_signature(data)
        if signature == self.last_signature:
            self.unchanged_polls += 1
        else:
            self.unchanged_polls = 0
            self.last_signature = signature
        self.last_successful_fetch = datetime.now(timezone.utc)

        if self._page_ready:
            self.refresh_board()
            self._send_status()
        else:
            self._pending_update = True

    def on_fetch_failed(self, error_message: str) -> None:
        logging.warning("Fetch failed: %s", error_message)
        self.last_fetch_ok = False
        self.consecutive_failures += 1
        self._send_status()

    def refresh_board(self) -> None:
        rows = build_board_rows(
            self.latest_data.messages if self.latest_data else [],
            self.config.max_cards,
        )
        data = json.dumps({"rows": rows})
        self._run_js(f"updateBoard({data})")

    def _send_status(self) -> None:
        data = self.latest_data
        last_update = data.last_updated if data else None

        is_stale = self._compute_staleness()
        has_delay = (
            data is not None
            and bool(data.messages)
            and has_delayed_visible_trains(data.messages, self.config.max_cards)
        )

        if is_stale:
            status = "STALE"
        elif has_delay:
            status = "DELAY"
        else:
            status = "LIVE"

        if last_update:
            display_time = last_update.astimezone().strftime("%I:%M:%S %p")
        else:
            display_time = "--:--:-- --"

        self._run_js(f"setStatus({json.dumps(status)}, {json.dumps(display_time)})")

    def _compute_staleness(self) -> bool:
        data = self.latest_data
        now = datetime.now(timezone.utc)

        ttl_seconds = self.config.ttl_seconds
        if data and data.messages:
            soonest = min(msg.seconds_to_arrival for msg in data.messages)
            if soonest < self.config.aggressive_threshold_seconds:
                ttl_seconds = self.config.ttl_aggressive_seconds
            else:
                ttl_seconds = max(ttl_seconds, int(self.config.poll_baseline_seconds * 1.5))

        stale_due_age = True
        if self.last_successful_fetch:
            age = (now - self.last_successful_fetch).total_seconds()
            stale_due_age = age > ttl_seconds

        has_messages = bool(data and data.messages)
        stale_no_change = self.unchanged_polls >= self.config.stale_no_change_polls
        stale_failures = self.consecutive_failures >= self.config.stale_failure_polls

        return (
            (not self.last_fetch_ok)
            or stale_due_age
            or (not has_messages)
            or stale_no_change
            or stale_failures
        )

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() == QtCore.Qt.Key.Key_Q and event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier:
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if hasattr(self, "_staleness_timer"):
            self._staleness_timer.stop()
        if hasattr(self, "fetch_thread"):
            self.fetch_thread.stop()
            self.fetch_thread.wait(2000)
        super().closeEvent(event)

    def _build_signature(self, data: StationData | None) -> tuple:
        if not data or not data.messages:
            return ()
        return tuple(
            (m.headsign, m.target, m.seconds_to_arrival, m.arrival_message, tuple(m.line_colors))
            for m in data.messages
        )


def main() -> int:
    setup_logging()
    config = load_config()

    for attr_name in ("AA_EnableHighDpiScaling", "AA_UseHighDpiPixmaps"):
        attr = getattr(QtCore.Qt.ApplicationAttribute, attr_name, None)
        if attr is not None:
            QtWidgets.QApplication.setAttribute(attr, True)
    rounding_policy = getattr(
        QtCore.Qt.HighDpiScaleFactorRoundingPolicy, "PassThrough", None
    )
    if rounding_policy is not None:
        QtWidgets.QApplication.setHighDpiScaleFactorRoundingPolicy(rounding_policy)

    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")

    window = MainWindow(config)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
