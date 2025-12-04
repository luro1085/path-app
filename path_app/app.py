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
                background-color: transparent;
                border-radius: 0px;
                color: #F5F7FA;
                border: none;
            }
            """
        )
        self.setMinimumHeight(110)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)

        self.fade_effect = QtWidgets.QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.fade_effect)
        self.fade_effect.setOpacity(1.0)
        self.fade_anim = QtCore.QPropertyAnimation(self.fade_effect, b"opacity", self)
        self.fade_anim.setDuration(260)
        self.fade_anim.setStartValue(0.0)
        self.fade_anim.setEndValue(1.0)

        self.strip = ColorStrip(
            self, orientation=QtCore.Qt.Orientation.Vertical
        )
        layout.addWidget(self.strip)

        body = QtWidgets.QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(10)
        self.headsign_label = QtWidgets.QLabel()
        self.headsign_label.setWordWrap(True)
        head_font = QtGui.QFont()
        head_font.setFamilies([f.strip() for f in font_family.split(",")])
        head_font.setPointSize(30)
        head_font.setBold(True)
        self.headsign_label.setFont(head_font)
        self.headsign_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        self.headsign_label.setStyleSheet("color: #E7ECF3;")

        self.arrival_label = QtWidgets.QLabel()
        self.arrival_label.setWordWrap(False)
        arr_font = QtGui.QFont()
        arr_font.setFamilies([f.strip() for f in font_family.split(",")])
        arr_font.setPointSize(48)
        arr_font.setBold(True)
        self.arrival_label.setFont(arr_font)
        self.arrival_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight
            | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        self.arrival_label.setMinimumWidth(0)
        self.arrival_label.setStyleSheet("color: #F2C94C;")

        body.addWidget(self.headsign_label, stretch=3)
        body.addWidget(self.arrival_label, stretch=1)
        layout.addLayout(body, stretch=1)

        # Direction/label row was requested to be hidden (only show headsign + time)
        self.direction_label = QtWidgets.QLabel()
        self.direction_label.setVisible(False)
        layout.addWidget(self.direction_label)

    def update_from(self, message: TrainMessage) -> None:
        self.strip.set_colors(message.line_colors)
        head = message.headsign or message.target
        primary_color = message.line_colors[0] if message.line_colors else "#E7ECF3"
        self.headsign_label.setStyleSheet(f"color: {primary_color};")
        self.headsign_label.setText(head.upper())

        # Arrival time keeps a consistent accent color
        self.arrival_label.setStyleSheet("color: #F2C94C;")
        self.arrival_label.setText(message.arrival_message or f"{message.seconds_to_arrival // 60} min")
        self.direction_label.setText("")
        self._run_fade()
        QtCore.QTimer.singleShot(0, self.adjust_font_sizes)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self.adjust_font_sizes()

    def adjust_font_sizes(self) -> None:
        fit_label(self.headsign_label, max_point_size=60, min_point_size=20, padding=4, wrap=True)
        fit_label(self.arrival_label, max_point_size=96, min_point_size=32, padding=4, wrap=False)

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
        self.setWindowFlag(QtCore.Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(QtCore.Qt.WindowType.WindowStaysOnTopHint, True)
        self.setFixedSize(1920, 720)
        self.setStyleSheet("background-color: #0A111A;")
        self.move(0, 0)

        self._build_ui()
        self._start_timers()

        self.fetch_thread = FetchThread(self.config)
        self.fetch_thread.data_received.connect(self.on_data_received)
        self.fetch_thread.fetch_failed.connect(self.on_fetch_failed)
        self.fetch_thread.start()

    def _build_ui(self) -> None:
        central = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(central)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(18)

        # Left area
        self.cards_container = QtWidgets.QWidget()
        self.cards_layout = QtWidgets.QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(10)
        self.cards_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.cards_container, stretch=5)

        self.card_widgets: List[CardWidget] = []
        self.placeholder = QtWidgets.QLabel("No upcoming trains posted")
        placeholder_font = QtGui.QFont()
        placeholder_font.setFamilies([f.strip() for f in self.config.font_family.split(",")])
        placeholder_font.setPointSize(26)
        self.placeholder.setFont(placeholder_font)
        self.placeholder.setStyleSheet("color: #7B8A9A;")
        self.placeholder.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.cards_layout.addWidget(self.placeholder)

        # Right area
        sidebar = QtWidgets.QFrame()
        self.sidebar = sidebar
        sidebar.setMinimumWidth(320)
        sidebar.setStyleSheet(
            "background-color: #0F1825; border-radius: 12px; color: #E7ECF3;"
        )
        side_layout = QtWidgets.QVBoxLayout(sidebar)
        side_layout.setContentsMargins(12, 8, 12, 4)
        side_layout.setSpacing(2)
        side_layout.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignTop
        )

        # Hoboken logo above status content
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

        # Top block with logo and info, allowing slight overlap upward
        top_block = QtWidgets.QWidget()
        top_layout = QtWidgets.QVBoxLayout(top_block)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(-50)
        top_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        top_layout.addWidget(
            self.hoboken_logo_label,
            alignment=QtCore.Qt.AlignmentFlag.AlignCenter,
        )

        info_container = QtWidgets.QWidget()
        info_container.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        info_layout = QtWidgets.QVBoxLayout(info_container)
        info_layout.setContentsMargins(0, -6, 0, 0)
        info_layout.setSpacing(6)
        info_layout.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignHCenter
            | QtCore.Qt.AlignmentFlag.AlignVCenter
        )

        self.clock_label = QtWidgets.QLabel("--:--")
        clock_font = QtGui.QFont()
        clock_font.setFamilies([f.strip() for f in self.config.font_family.split(",")])
        clock_font.setPointSize(46)
        clock_font.setBold(True)
        self.clock_label.setFont(clock_font)
        self.clock_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        info_layout.addWidget(self.clock_label)

        self.day_label = QtWidgets.QLabel("")
        day_font = QtGui.QFont()
        day_font.setFamilies([f.strip() for f in self.config.font_family.split(",")])
        day_font.setPointSize(18)
        self.day_label.setFont(day_font)
        self.day_label.setStyleSheet("color: #9FB3C8;")
        self.day_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        info_layout.addWidget(self.day_label)

        self.last_updated_label = QtWidgets.QLabel("Last updated: --:--:--")
        last_font = QtGui.QFont()
        last_font.setFamilies([f.strip() for f in self.config.font_family.split(",")])
        last_font.setPointSize(18)
        self.last_updated_label.setFont(last_font)
        self.last_updated_label.setStyleSheet("color: #C9D7E3;")
        self.last_updated_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        info_layout.addWidget(self.last_updated_label)

        self.status_pill = StatusPill(self.config.font_family)
        info_layout.addWidget(
            self.status_pill, alignment=QtCore.Qt.AlignmentFlag.AlignCenter
        )

        top_layout.addWidget(info_container, stretch=1)
        top_block.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Maximum,
        )
        side_layout.addWidget(top_block)
        # Push the PATH logo downward slightly with a fixed spacer
        side_layout.addItem(
            QtWidgets.QSpacerItem(
                0,
                40,
                QtWidgets.QSizePolicy.Policy.Minimum,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
        )

        # PATH logo beneath status panel
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
        layout.addWidget(sidebar, stretch=1)

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
            return

        self.placeholder.hide()
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
        else:
            self.last_updated_label.setText("Last updated: --:--:--")

        has_messages = bool(data and data.messages)
        stale_no_change = self.unchanged_polls >= self.config.stale_no_change_polls
        stale_failures = self.consecutive_failures >= self.config.stale_failure_polls
        is_stale = (not self.last_fetch_ok) or stale_due_age or (not has_messages) or stale_no_change or stale_failures
        self.status_pill.set_live(not is_stale)
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
