from __future__ import annotations

import re
from typing import Any

from .path_data import TrainMessage

GRID_COLS = 20
MAX_DEPARTURE_ROWS = 5
EMPTY_STATE_ROW_INDEX = 2

HEADSIGN_ABBREV = {
    "World Trade Center": "WORLD TRADE",
    "Journal Square": "JOURNAL SQ",
    "33rd Street": "33RD ST",
    "Newark": "NEWARK",
    "Hoboken": "HOBOKEN",
    "Christopher Street": "CHRIS ST",
}


def abbreviate_headsign(headsign: str) -> str:
    """Shorten headsign to fit the split-flap grid."""
    base = re.split(r"\s+via\s+", headsign, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    if not base:
        return ""
    return HEADSIGN_ABBREV.get(base, base.upper()[:12])


def compact_arrival_text(arrival_message: str, *, is_presumed: bool = False) -> str:
    """Compress an arrival label to fit the 20-column board."""
    text = " ".join(arrival_message.strip().upper().split())
    if is_presumed and text and not text.startswith("~"):
        text = "~" + text

    minute_match = re.fullmatch(r"(~?)(\d+)\s*MIN", text)
    if minute_match:
        if minute_match.group(2) == "0":
            return "DUE"
        return f"{minute_match.group(1)}{minute_match.group(2)}MIN"
    if text == "BOARDING":
        return "BOARD"
    if text == "DELAYED":
        return "DELAY"
    return text.replace(" ", "")[:6]


def center_text(text: str, width: int = GRID_COLS) -> str:
    """Center text within the board width."""
    trimmed = text[:width]
    pad = max(0, width - len(trimmed))
    left_pad = pad // 2
    return " " * left_pad + trimmed + " " * (pad - left_pad)


def visible_departure_limit(max_cards: int) -> int:
    """Clamp configured train rows to the board capacity."""
    return max(0, min(max_cards, MAX_DEPARTURE_ROWS))


def format_train_row(msg: TrainMessage) -> str:
    """Format a single train departure as a fixed-width row."""
    dest = abbreviate_headsign(msg.headsign)
    time_str = compact_arrival_text(
        msg.arrival_message,
        is_presumed=msg.backfill_source is not None,
    )
    gap = GRID_COLS - len(dest) - len(time_str)
    if gap < 1:
        dest = dest[:GRID_COLS - len(time_str) - 1]
        gap = 1
    return dest + " " * gap + time_str


def pick_line_color(msg: TrainMessage) -> str:
    """Pick the primary display color for a train message."""
    if not msg.line_colors:
        return "#FFFFFF"
    if msg.label == "ToNJ" and len(msg.line_colors) > 1:
        return msg.line_colors[1]
    return msg.line_colors[0]


def build_train_row_colors(msg: TrainMessage, row_text: str) -> list[Any]:
    """Build per-tile colors so ETA digits use route-colored tiles."""
    route_color = pick_line_color(msg)
    colors: list[Any] = [route_color] * GRID_COLS
    time_text = compact_arrival_text(
        msg.arrival_message,
        is_presumed=msg.backfill_source is not None,
    )
    time_start = len(row_text) - len(time_text)

    if time_text == "DUE":
        for idx in range(time_start, min(time_start + 3, GRID_COLS)):
            colors[idx] = {"fg": "#FFFFFF", "bg": route_color}
        return colors

    match = re.match(r"~?\d+", time_text)
    if not match:
        return colors

    highlight_end = time_start + len(match.group(0))
    for idx in range(time_start, min(highlight_end, GRID_COLS)):
        colors[idx] = {"fg": "#FFFFFF", "bg": route_color}
    return colors


def has_delayed_visible_trains(messages: list[TrainMessage], max_cards: int) -> bool:
    """Return True if any visible train has a 'Delayed' arrival message."""
    visible = messages[: visible_departure_limit(max_cards)]
    return any(msg.arrival_message.strip().upper() == "DELAYED" for msg in visible)


def build_board_rows(messages: list[TrainMessage], max_cards: int) -> list[dict[str, Any]]:
    """Build the five departure rows displayed on the board."""
    visible_messages = messages[: visible_departure_limit(max_cards)]

    rows: list[dict[str, Any]] = []
    if not messages:
        for i in range(MAX_DEPARTURE_ROWS):
            if i == EMPTY_STATE_ROW_INDEX:
                rows.append({
                    "text": center_text("NO TRAINS POSTED"),
                    "color": "#7B8A9A",
                })
            else:
                rows.append({"text": "", "color": "#FFFFFF"})
        return rows

    for msg in visible_messages:
        row_text = format_train_row(msg)
        rows.append({
            "text": row_text,
            "color": build_train_row_colors(msg, row_text),
        })

    while len(rows) < MAX_DEPARTURE_ROWS:
        rows.append({"text": "", "color": "#FFFFFF"})

    return rows


__all__ = [
    "GRID_COLS",
    "MAX_DEPARTURE_ROWS",
    "EMPTY_STATE_ROW_INDEX",
    "abbreviate_headsign",
    "compact_arrival_text",
    "center_text",
    "visible_departure_limit",
    "format_train_row",
    "pick_line_color",
    "build_train_row_colors",
    "has_delayed_visible_trains",
    "build_board_rows",
]
