from __future__ import annotations

import logging
import sys
import threading
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import List, Optional
import random

import requests
from PyQt6 import QtCore, QtGui, QtWidgets

from .config import AppConfig, load_config
from .path_data import StationData, TrainMessage, parse_station_data, top_messages

LOG_PATH = Path("logs/app.log")
FEED_URL = "https://www.panynj.gov/bin/portauthority/ridepath.json"
LOGO_PATH = Path("PATH_logo.png")
HOBOKEN_LOGO_PATH = Path("Hoboken_logo-final_Teal_Round.png")
LOGO_ASPECT = 2560 / 1318
ICON_PATH = Path("app-icon.ico") if Path("app-icon.ico").exists() else Path("app-icon.png")


def fit_label(
    label: QtWidgets.QLabel,
    max_point_size: float,
    min_point_size: float = 8,
    padding: int = 0,
    wrap: bool = False,
) -> None:
    """Shrink text until it fits within the label's current box."""
    if label.width() <= 0 or label.height() <= 0:
        return
    text = label.text()
    if not text:
        return
    avail_w = max(4, label.width() - padding)
    avail_h = max(4, label.height() - padding)
    flags = QtCore.Qt.TextFlag.TextWordWrap if wrap else QtCore.Qt.TextFlag(0)
    align_flags = (
        QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop
    )
    chosen_size = min_point_size
    font = QtGui.QFont(label.font())
    size = max_point_size
    while size >= min_point_size:
        font.setPointSizeF(size)
        metrics = QtGui.QFontMetrics(font)
        if wrap:
            rect = metrics.boundingRect(
                QtCore.QRect(0, 0, avail_w, 10_000),
                int(flags | align_flags),
                text,
            )
        else:
            rect = metrics.boundingRect(text)
        if rect.width() <= avail_w and rect.height() <= avail_h:
            chosen_size = size
            break
        size -= 1
    font.setPointSizeF(chosen_size)
    label.setFont(font)


def setup_logging() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(LOG_PATH, maxBytes=512_000, backupCount=3)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=[handler])


def ensure_dpi_awareness() -> None:
    """Opt into per-monitor DPI awareness on Windows for crisp text."""
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass


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
        resp = self.session.get(FEED_URL, timeout=5)
        resp.raise_for_status()
        return parse_station_data(resp.json(), self.config.station)

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


class ColorStrip(QtWidgets.QWidget):
    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget] = None,
        orientation: QtCore.Qt.Orientation = QtCore.Qt.Orientation.Horizontal,
    ) -> None:
        super().__init__(parent)
        self.orientation = orientation
        if orientation == QtCore.Qt.Orientation.Horizontal:
            self.setFixedHeight(8)
            self.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
        else:
            self.setFixedWidth(12)
            self.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Fixed,
                QtWidgets.QSizePolicy.Policy.Expanding,
            )

    def set_colors(self, colors: List[str]) -> None:
        if not colors:
            colors = ["#999999"]
        if len(colors) == 1:
            style = f"background-color: {colors[0]};"
        else:
            c1, c2 = colors[0], colors[1]
            direction = (
                "x1:0, y1:0, x2:1, y2:0"
                if self.orientation == QtCore.Qt.Orientation.Horizontal
                else "x1:0, y1:0, x2:0, y2:1"
            )
            style = (
                f"background: qlineargradient({direction}, "
                f"stop:0 {c1}, stop:0.5 {c1}, stop:0.5 {c2}, stop:1 {c2});"
            )
        self.setStyleSheet(style)


class CardWidget(QtWidgets.QFrame):
    def __init__(self, font_family: str, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.setStyleSheet(
            """
            QFrame#card {
                background-color: rgba(18, 25, 38, 0.92);
                border-radius: 18px;
                color: #F5F7FA;
                border: 1px solid #1C2A3A;
            }
            QLabel#pillLabel {
                background-color: rgba(255, 255, 255, 0.08);
                color: #9FB3C8;
                padding: 4px 10px;
                border-radius: 12px;
                font-weight: 700;
                letter-spacing: 0.8px;
            }
            """
        )
        self.setMinimumHeight(120)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.fade_effect = QtWidgets.QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.fade_effect)
        self.fade_effect.setOpacity(1.0)
        self.fade_anim = QtCore.QPropertyAnimation(self.fade_effect, b"opacity", self)
        self.fade_anim.setDuration(260)
        self.fade_anim.setStartValue(0.0)
        self.fade_anim.setEndValue(1.0)

        self.strip = ColorStrip(
            self, orientation=QtCore.Qt.Orientation.Horizontal
        )
        layout.addWidget(self.strip)

        body = QtWidgets.QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(12)

        left_col = QtWidgets.QVBoxLayout()
        left_col.setSpacing(6)
        badge_row = QtWidgets.QHBoxLayout()
        badge_row.setSpacing(8)

        self.line_badge = QtWidgets.QLabel()
        badge_font = QtGui.QFont()
        badge_font.setFamilies([f.strip() for f in font_family.split(",")])
        badge_font.setPointSize(14)
        badge_font.setBold(True)
        self.line_badge.setFont(badge_font)
        self.line_badge.setObjectName("pillLabel")
        self.line_badge.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignCenter | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        badge_row.addWidget(self.line_badge, 0, QtCore.Qt.AlignmentFlag.AlignLeft)
        badge_row.addStretch(1)
        left_col.addLayout(badge_row)

        self.headsign_label = QtWidgets.QLabel()
        self.headsign_label.setWordWrap(True)
        head_font = QtGui.QFont()
        head_font.setFamilies([f.strip() for f in font_family.split(",")])
        head_font.setPointSize(32)
        head_font.setBold(True)
        self.headsign_label.setFont(head_font)
        self.headsign_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        self.headsign_label.setStyleSheet("color: #E7ECF3;")
        left_col.addWidget(self.headsign_label)

        self.meta_label = QtWidgets.QLabel()
        meta_font = QtGui.QFont()
        meta_font.setFamilies([f.strip() for f in font_family.split(",")])
        meta_font.setPointSize(16)
        self.meta_label.setFont(meta_font)
        self.meta_label.setStyleSheet("color: #9FB3C8;")
        self.meta_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        self.meta_label.setWordWrap(True)
        left_col.addWidget(self.meta_label)

        body.addLayout(left_col, stretch=3)

        right_col = QtWidgets.QVBoxLayout()
        right_col.setSpacing(4)
        right_col.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self.arrival_label = QtWidgets.QLabel()
        self.arrival_label.setWordWrap(False)
        arr_font = QtGui.QFont()
        arr_font.setFamilies([f.strip() for f in font_family.split(",")])
        arr_font.setPointSize(54)
        arr_font.setBold(True)
        self.arrival_label.setFont(arr_font)
        self.arrival_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight
            | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        self.arrival_label.setMinimumWidth(0)
        self.arrival_label.setStyleSheet("color: #F2C94C;")
        right_col.addWidget(self.arrival_label, 0, QtCore.Qt.AlignmentFlag.AlignRight)

        self.subtle_label = QtWidgets.QLabel()
        subtle_font = QtGui.QFont()
        subtle_font.setFamilies([f.strip() for f in font_family.split(",")])
        subtle_font.setPointSize(14)
        self.subtle_label.setFont(subtle_font)
        self.subtle_label.setStyleSheet("color: #9FB3C8;")
        self.subtle_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight
            | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        right_col.addWidget(self.subtle_label, 0, QtCore.Qt.AlignmentFlag.AlignRight)

        body.addLayout(right_col, stretch=1)
        layout.addLayout(body, stretch=1)

        self.direction_label = QtWidgets.QLabel()
        self.direction_label.setVisible(False)
        layout.addWidget(self.direction_label)

    def update_from(self, message: TrainMessage) -> None:
        self.strip.set_colors(message.line_colors)
        head = message.headsign or message.target or "PATH"
        primary_color = message.line_colors[0] if message.line_colors else "#E7ECF3"
        self.headsign_label.setStyleSheet(f"color: {primary_color};")
        self.headsign_label.setText(head.upper())

        line_name = message.label.strip() if message.label else "PATH"
        self.line_badge.setText(line_name.upper())
        meta_parts = [part for part in [message.target, message.headsign] if part]
        self.meta_label.setText(" • ".join(meta_parts) if meta_parts else "On time service")

        arrival_text = message.arrival_message or f"{message.seconds_to_arrival // 60} min"
        self.arrival_label.setText(arrival_text)
        self.subtle_label.setText("Updated feed")
        self.direction_label.setText("")
        self._run_fade()
        QtCore.QTimer.singleShot(0, self.adjust_font_sizes)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self.adjust_font_sizes()

    def adjust_font_sizes(self) -> None:
        fit_label(self.line_badge, max_point_size=18, min_point_size=10, padding=2)
        fit_label(self.headsign_label, max_point_size=58, min_point_size=18, padding=4, wrap=True)
        fit_label(self.meta_label, max_point_size=22, min_point_size=12, padding=4, wrap=True)
        fit_label(self.arrival_label, max_point_size=96, min_point_size=36, padding=4, wrap=False)
        fit_label(self.subtle_label, max_point_size=18, min_point_size=10, padding=2, wrap=False)

    def _run_fade(self) -> None:
        if self.fade_anim.state() == QtCore.QAbstractAnimation.State.Running:
            self.fade_anim.stop()
        self.fade_effect.setOpacity(0.0)
        self.fade_anim.start()


class StatusPill(QtWidgets.QLabel):
    def __init__(self, font_family: str, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        font = QtGui.QFont()
        font.setFamilies([f.strip() for f in font_family.split(",")])
        font.setPointSize(20)
        font.setBold(True)
        self.setFont(font)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setMinimumWidth(160)
        self.setMinimumHeight(52)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.setObjectName("pill")
        self.setStyleSheet(
            """
            QLabel#pill {
                border-radius: 18px;
                color: #0D141F;
                background-color: #56CC9D;
            }
            """
        )

    def set_live(self, live: bool) -> None:
        if live:
            self.setText("LIVE")
            self.setStyleSheet(
                """
                QLabel#pill {
                    border-radius: 18px;
                    color: #0D141F;
                    background-color: #56CC9D;
                }
                """
            )
        else:
            self.setText("STALE")
            self.setStyleSheet(
                """
                QLabel#pill {
                    border-radius: 18px;
                    color: #0D141F;
                    background-color: #E0A800;
                }
                """
            )


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

        self.setWindowTitle("PATH Arrivals - Hoboken")
        if ICON_PATH.exists():
            self.setWindowIcon(QtGui.QIcon(str(ICON_PATH)))
        self.setWindowFlag(QtCore.Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(QtCore.Qt.WindowType.WindowStaysOnTopHint, True)
        self.setFixedSize(1920, 720)
        self.setStyleSheet("background-color: #070C14;")
        self.move(0, 0)

        self._build_ui()
        self._start_timers()

        self.fetch_thread = FetchThread(self.config)
        self.fetch_thread.data_received.connect(self.on_data_received)
        self.fetch_thread.fetch_failed.connect(self.on_fetch_failed)
        self.fetch_thread.start()

    def _build_ui(self) -> None:
        central = QtWidgets.QWidget()
        central.setObjectName("surface")
        central.setStyleSheet(
            """
            QWidget#surface {
                background: qradialgradient(cx:0.1, cy:0.1, radius: 1.4, fx:0.3, fy:0.3,
                    stop:0 #122032, stop:0.35 #0B1523, stop:1 #070C14);
            }
            """
        )
        main_layout = QtWidgets.QVBoxLayout(central)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        header = QtWidgets.QFrame()
        header.setObjectName("header")
        header.setStyleSheet(
            """
            QFrame#header {
                background-color: rgba(255, 255, 255, 0.02);
                border: 1px solid #1B2738;
                border-radius: 18px;
            }
            """
        )
        header_layout = QtWidgets.QHBoxLayout(header)
        header_layout.setContentsMargins(20, 16, 20, 16)
        header_layout.setSpacing(18)

        title_stack = QtWidgets.QVBoxLayout()
        title_stack.setSpacing(8)
        self.title_label = QtWidgets.QLabel("PATH ARRIVALS")
        title_font = QtGui.QFont()
        title_font.setFamilies([f.strip() for f in self.config.font_family.split(",")])
        title_font.setPointSize(26)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        self.title_label.setStyleSheet("color: #E7ECF3; letter-spacing: 1.4px;")
        title_stack.addWidget(self.title_label)

        chip_row = QtWidgets.QHBoxLayout()
        chip_row.setSpacing(10)
        self.station_chip = QtWidgets.QLabel(f"Station {self.config.station}")
        chip_font = QtGui.QFont()
        chip_font.setFamilies([f.strip() for f in self.config.font_family.split(",")])
        chip_font.setPointSize(14)
        chip_font.setBold(True)
        self.station_chip.setFont(chip_font)
        self.station_chip.setStyleSheet(
            "color: #B7C7D9; background-color: rgba(255,255,255,0.08);"
            " padding: 6px 12px; border-radius: 14px;"
        )
        chip_row.addWidget(self.station_chip, 0, QtCore.Qt.AlignmentFlag.AlignLeft)
        chip_row.addStretch(1)
        title_stack.addLayout(chip_row)

        subtitle = QtWidgets.QLabel("Live board with real-time train departures")
        subtitle_font = QtGui.QFont()
        subtitle_font.setFamilies([f.strip() for f in self.config.font_family.split(",")])
        subtitle_font.setPointSize(14)
        subtitle.setFont(subtitle_font)
        subtitle.setStyleSheet("color: #8FA4BC;")
        title_stack.addWidget(subtitle)
        header_layout.addLayout(title_stack, stretch=3)

        time_stack = QtWidgets.QVBoxLayout()
        time_stack.setSpacing(6)
        time_stack.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)

        self.clock_label = QtWidgets.QLabel("--:--")
        clock_font = QtGui.QFont()
        clock_font.setFamilies([f.strip() for f in self.config.font_family.split(",")])
        clock_font.setPointSize(54)
        clock_font.setBold(True)
        self.clock_label.setFont(clock_font)
        self.clock_label.setStyleSheet("color: #F6F9FD;")
        self.clock_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        time_stack.addWidget(self.clock_label)

        self.day_label = QtWidgets.QLabel("")
        day_font = QtGui.QFont()
        day_font.setFamilies([f.strip() for f in self.config.font_family.split(",")])
        day_font.setPointSize(18)
        self.day_label.setFont(day_font)
        self.day_label.setStyleSheet("color: #9FB3C8;")
        self.day_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        time_stack.addWidget(self.day_label)

        self.last_updated_label = QtWidgets.QLabel("Last updated: --:--:--")
        last_font = QtGui.QFont()
        last_font.setFamilies([f.strip() for f in self.config.font_family.split(",")])
        last_font.setPointSize(16)
        self.last_updated_label.setFont(last_font)
        self.last_updated_label.setStyleSheet("color: #C9D7E3;")
        self.last_updated_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        time_stack.addWidget(self.last_updated_label)

        self.status_pill = StatusPill(self.config.font_family)
        time_stack.addWidget(
            self.status_pill, alignment=QtCore.Qt.AlignmentFlag.AlignRight
        )
        header_layout.addLayout(time_stack, stretch=2)
        main_layout.addWidget(header)

        content_layout = QtWidgets.QHBoxLayout()
        content_layout.setSpacing(18)
        content_layout.setContentsMargins(0, 0, 0, 0)

        cards_panel = QtWidgets.QFrame()
        cards_panel.setObjectName("cardsPanel")
        cards_panel.setStyleSheet(
            """
            QFrame#cardsPanel {
                background-color: rgba(10, 16, 26, 0.86);
                border: 1px solid #162234;
                border-radius: 18px;
            }
            """
        )
        cards_panel_layout = QtWidgets.QVBoxLayout(cards_panel)
        cards_panel_layout.setContentsMargins(16, 16, 16, 16)
        cards_panel_layout.setSpacing(12)

        header_row = QtWidgets.QHBoxLayout()
        header_row.setSpacing(8)
        upcoming_label = QtWidgets.QLabel("Upcoming departures")
        upcoming_font = QtGui.QFont()
        upcoming_font.setFamilies([f.strip() for f in self.config.font_family.split(",")])
        upcoming_font.setPointSize(18)
        upcoming_font.setBold(True)
        upcoming_label.setFont(upcoming_font)
        upcoming_label.setStyleSheet("color: #E7ECF3;")
        header_row.addWidget(upcoming_label)
        header_row.addStretch(1)
        cards_panel_layout.addLayout(header_row)

        self.cards_container = QtWidgets.QWidget()
        self.cards_layout = QtWidgets.QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(10)
        self.cards_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        cards_panel_layout.addWidget(self.cards_container)

        self.card_widgets: List[CardWidget] = []
        self.placeholder = QtWidgets.QLabel("No upcoming trains posted")
        placeholder_font = QtGui.QFont()
        placeholder_font.setFamilies([f.strip() for f in self.config.font_family.split(",")])
        placeholder_font.setPointSize(24)
        placeholder_font.setBold(True)
        self.placeholder.setFont(placeholder_font)
        self.placeholder.setStyleSheet(
            "color: #6E7E95; background-color: rgba(255,255,255,0.03);"
            " border: 1px dashed #2A3B53; border-radius: 14px; padding: 22px;"
        )
        self.placeholder.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.cards_layout.addWidget(self.placeholder)

        content_layout.addWidget(cards_panel, stretch=3)

        sidebar = QtWidgets.QFrame()
        self.sidebar = sidebar
        sidebar.setMinimumWidth(360)
        sidebar.setObjectName("sidebar")
        sidebar.setStyleSheet(
            """
            QFrame#sidebar {
                background-color: rgba(13, 20, 31, 0.92);
                border-radius: 18px;
                border: 1px solid #162234;
                color: #E7ECF3;
            }
            """
        )
        side_layout = QtWidgets.QVBoxLayout(sidebar)
        side_layout.setContentsMargins(16, 14, 16, 10)
        side_layout.setSpacing(12)
        side_layout.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignTop
        )

        self.hoboken_logo_label = QtWidgets.QLabel()
        self.hoboken_logo_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        self.hoboken_logo_label.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        self.hoboken_logo_pixmap = (
            QtGui.QPixmap(str(HOBOKEN_LOGO_PATH))
            if HOBOKEN_LOGO_PATH.exists()
            else QtGui.QPixmap()
        )
        if self.hoboken_logo_pixmap.isNull():
            hoboken_font = QtGui.QFont()
            hoboken_font.setFamilies([f.strip() for f in self.config.font_family.split(",")])
            hoboken_font.setPointSize(18)
            hoboken_font.setBold(True)
            self.hoboken_logo_label.setFont(hoboken_font)
            self.hoboken_logo_label.setStyleSheet("color: #56CC9D;")
            self.hoboken_logo_label.setText("HOBOKEN")
        side_layout.addWidget(self.hoboken_logo_label)

        highlight = QtWidgets.QLabel("Service summary")
        highlight_font = QtGui.QFont()
        highlight_font.setFamilies([f.strip() for f in self.config.font_family.split(",")])
        highlight_font.setPointSize(16)
        highlight_font.setBold(True)
        highlight.setFont(highlight_font)
        highlight.setStyleSheet("color: #E7ECF3;")
        side_layout.addWidget(highlight, 0, QtCore.Qt.AlignmentFlag.AlignLeft)

        self.feed_status_value = QtWidgets.QLabel("Checking feed…")
        self.feed_status_value.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        feed_font = QtGui.QFont()
        feed_font.setFamilies([f.strip() for f in self.config.font_family.split(",")])
        feed_font.setPointSize(22)
        feed_font.setBold(True)
        self.feed_status_value.setFont(feed_font)
        self.feed_status_value.setStyleSheet("color: #56CC9D;")
        side_layout.addWidget(self.feed_status_value)

        self.trains_count_value = QtWidgets.QLabel("0 trains posted")
        self.trains_count_value.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        count_font = QtGui.QFont()
        count_font.setFamilies([f.strip() for f in self.config.font_family.split(",")])
        count_font.setPointSize(18)
        self.trains_count_value.setFont(count_font)
        self.trains_count_value.setStyleSheet("color: #9FB3C8;")
        side_layout.addWidget(self.trains_count_value)

        side_layout.addStretch(1)

        self.logo_label = QtWidgets.QLabel()
        self.logo_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        self.logo_label.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Maximum,
        )
        self.logo_pixmap = QtGui.QPixmap(str(LOGO_PATH)) if LOGO_PATH.exists() else QtGui.QPixmap()
        if self.logo_pixmap.isNull():
            logo_font = QtGui.QFont()
            logo_font.setFamilies([f.strip() for f in self.config.font_family.split(",")])
            logo_font.setPointSize(20)
            logo_font.setBold(True)
            self.logo_label.setFont(logo_font)
            self.logo_label.setStyleSheet("color: #E7ECF3;")
            self.logo_label.setText("PATH")
        side_layout.addWidget(
            self.logo_label, alignment=QtCore.Qt.AlignmentFlag.AlignCenter
        )
        QtCore.QTimer.singleShot(0, self.update_logo_size)
        content_layout.addWidget(sidebar, stretch=1)

        main_layout.addLayout(content_layout)
        self.setCentralWidget(central)

    def _start_timers(self) -> None:
        self.clock_timer = QtCore.QTimer(self)
        self.clock_timer.setInterval(1000)
        self.clock_timer.timeout.connect(self.update_clock)
        self.clock_timer.start()
        QtCore.QTimer.singleShot(0, self.adjust_sidebar_fonts)

    def update_clock(self) -> None:
        now = datetime.now()
        self.clock_label.setText(now.strftime("%H:%M"))
        self.day_label.setText(now.strftime("%A"))
        self.update_status_pill()
        self.adjust_sidebar_fonts()

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
        self.refresh_cards()
        self.update_status_pill()

    def on_fetch_failed(self, error_message: str) -> None:
        logging.warning("Fetch failed: %s", error_message)
        self.last_fetch_ok = False
        self.consecutive_failures += 1
        self.update_status_pill()

    def refresh_cards(self) -> None:
        messages = top_messages(self.latest_data.messages if self.latest_data else [], self.config.max_cards)
        if not messages:
            for widget in self.card_widgets:
                widget.hide()
            self.placeholder.show()
            self.trains_count_value.setText("0 trains posted")
            return

        self.placeholder.hide()
        self.trains_count_value.setText(f"{len(messages)} trains posted")
        # Update existing widgets or add/remove to match message count
        while len(self.card_widgets) < len(messages):
            card = CardWidget(self.config.font_family, self.cards_container)
            card.setMinimumHeight(110)
            card.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Preferred,
            )
            self.cards_layout.addWidget(card)
            self.card_widgets.append(card)

        while len(self.card_widgets) > len(messages):
            widget = self.card_widgets.pop()
            self.cards_layout.removeWidget(widget)
            widget.setParent(None)
            widget.deleteLater()

        for card, message in zip(self.card_widgets, messages):
            card.update_from(message)
            card.show()
            card.adjust_font_sizes()

    def update_status_pill(self) -> None:
        data = self.latest_data
        last_update = data.last_updated if data else None
        now = datetime.now(timezone.utc)
        stale_due_age = True
        ttl_seconds = self.config.ttl_seconds
        if data and data.messages:
            soonest = min(msg.seconds_to_arrival for msg in data.messages)
            if soonest < self.config.aggressive_threshold_seconds:
                ttl_seconds = self.config.ttl_aggressive_seconds
            else:
                ttl_seconds = max(ttl_seconds, int(self.config.poll_baseline_seconds * 1.5))
        if self.last_successful_fetch:
            age = (now - self.last_successful_fetch).total_seconds()
            stale_due_age = age > ttl_seconds
        if last_update:
            display_time = last_update.astimezone().strftime("%H:%M:%S")
            self.last_updated_label.setText(f"Last updated: {display_time}")
        elif self.last_successful_fetch:
            display_time = self.last_successful_fetch.astimezone().strftime("%H:%M:%S")
            self.last_updated_label.setText(f"Last fetched: {display_time}")
        else:
            self.last_updated_label.setText("Last updated: --:--:--")

        has_messages = bool(data and data.messages)
        stale_no_change = self.unchanged_polls >= self.config.stale_no_change_polls
        stale_failures = self.consecutive_failures >= self.config.stale_failure_polls
        is_stale = (not self.last_fetch_ok) or stale_due_age or (not has_messages) or stale_no_change or stale_failures
        self.status_pill.set_live(not is_stale)
        status_text = "Live feed" if not is_stale else "Stale feed"
        status_color = "#56CC9D" if not is_stale else "#E0A800"
        self.feed_status_value.setText(status_text)
        self.feed_status_value.setStyleSheet(f"color: {status_color};")
        self.adjust_sidebar_fonts()

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() == QtCore.Qt.Key.Key_Q and event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier:
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if hasattr(self, "fetch_thread"):
            self.fetch_thread.stop()
            self.fetch_thread.wait(2000)
        super().closeEvent(event)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        self.update_logo_size()
        super().resizeEvent(event)
        QtCore.QTimer.singleShot(0, self.adjust_sidebar_fonts)

    def update_logo_size(self) -> None:
        sidebar_width = self.sidebar.width() if hasattr(self, "sidebar") else 300
        sidebar_height = self.sidebar.height() if hasattr(self, "sidebar") else 400
        margin_allowance = 36
        max_width = max(120, sidebar_width - margin_allowance)
        # Keep top logo modest; leave room for text stack
        self._scale_logo(
            label=getattr(self, "hoboken_logo_label", None),
            pixmap=getattr(self, "hoboken_logo_pixmap", None),
            max_width=max_width,
            max_height=max(240, int(sidebar_height * 0.45)),
        )

        # Bottom PATH logo uses the lower half
        self._scale_logo(
            label=getattr(self, "logo_label", None),
            pixmap=getattr(self, "logo_pixmap", None),
            max_width=max_width,
            max_height=max(100, int(sidebar_height * 0.3)),
            aspect=LOGO_ASPECT,
        )

    def _build_signature(self, data: StationData | None) -> tuple:
        if not data or not data.messages:
            return ()
        return tuple(
            (m.headsign, m.target, m.seconds_to_arrival, m.arrival_message, tuple(m.line_colors))
            for m in data.messages
        )

    def adjust_sidebar_fonts(self) -> None:
        fit_label(self.clock_label, max_point_size=96, min_point_size=46, padding=6)
        fit_label(self.day_label, max_point_size=40, min_point_size=18, padding=4)
        fit_label(self.last_updated_label, max_point_size=34, min_point_size=16, padding=6, wrap=True)
        fit_label(self.status_pill, max_point_size=30, min_point_size=16, padding=12)

    def _scale_logo(
        self,
        label: Optional[QtWidgets.QLabel],
        pixmap: Optional[QtGui.QPixmap],
        max_width: int,
        max_height: int,
        aspect: Optional[float] = None,
    ) -> None:
        if not label:
            return
        if pixmap is None or pixmap.isNull():
            label.setFixedHeight(max_height)
            return

        if aspect:
            target_width = min(max_width, int(max_height * aspect))
            target_height = int(target_width / aspect)
            if target_height > max_height:
                target_height = max_height
                target_width = int(target_height * aspect)
        else:
            ratio = pixmap.width() / pixmap.height() if pixmap.height() else 1
            target_width = min(max_width, int(max_height * ratio))
            target_height = int(target_width / ratio) if ratio else max_height
            if target_height > max_height:
                target_height = max_height
                target_width = int(target_height * ratio) if ratio else max_width

        scaled = pixmap.scaled(
            target_width,
            target_height,
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        label.setPixmap(scaled)
        label.setFixedSize(target_width, target_height)


def main() -> int:
    setup_logging()
    config = load_config()

    for attr_name in ("AA_EnableHighDpiScaling", "AA_UseHighDpiPixmaps"):
        attr = getattr(QtCore.Qt.ApplicationAttribute, attr_name, None)
        if attr is not None:
            QtWidgets.QApplication.setAttribute(attr, True)
    # Prefer crisp scaling on HiDPI displays if available.
    rounding_policy = getattr(
        QtCore.Qt.HighDpiScaleFactorRoundingPolicy, "PassThrough", None
    )
    if rounding_policy is not None:
        QtWidgets.QApplication.setHighDpiScaleFactorRoundingPolicy(rounding_policy)

    app = QtWidgets.QApplication(sys.argv)
    font = QtGui.QFont()
    font.setFamilies([f.strip() for f in config.font_family.split(",")])
    font.setPointSize(12)
    app.setFont(font)
    app.setStyle("Fusion")

    window = MainWindow(config)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
