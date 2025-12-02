from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, List, Optional


@dataclass
class TrainMessage:
    label: str
    target: str
    seconds_to_arrival: int
    arrival_message: str
    line_colors: List[str]
    headsign: str
    last_updated: Optional[datetime]


@dataclass
class StationData:
    messages: List[TrainMessage]
    last_updated: Optional[datetime]


def _normalize_color(value: str) -> str:
    value = value.strip().lstrip("#")
    if len(value) == 0:
        return "#999999"
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    return f"#{value.upper()}"


def parse_line_colors(raw: str) -> List[str]:
    if not raw:
        return ["#999999"]
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    if not parts:
        return ["#999999"]
    normalized = [_normalize_color(part) for part in parts]
    return normalized[:2]


def parse_last_updated(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def parse_station_data(payload: Any, station_code: str) -> StationData:
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        return StationData(messages=[], last_updated=None)

    station_entry = next(
        (entry for entry in results if entry.get("consideredStation") == station_code),
        None,
    )
    if not station_entry:
        return StationData(messages=[], last_updated=None)

    messages: List[TrainMessage] = []
    for destination in station_entry.get("destinations", []):
        label = destination.get("label", "")
        for raw_msg in destination.get("messages", []):
            try:
                seconds = int(raw_msg.get("secondsToArrival", "0"))
            except (TypeError, ValueError):
                continue
            message = TrainMessage(
                label=label,
                target=str(raw_msg.get("target", "")).strip(),
                seconds_to_arrival=seconds,
                arrival_message=str(raw_msg.get("arrivalTimeMessage", "")).strip(),
                line_colors=parse_line_colors(str(raw_msg.get("lineColor", ""))),
                headsign=str(raw_msg.get("headSign", "")).strip(),
                last_updated=parse_last_updated(raw_msg.get("lastUpdated")),
            )
            messages.append(message)

    messages.sort(key=lambda m: m.seconds_to_arrival)
    last_updated = max(
        (msg.last_updated for msg in messages if msg.last_updated), default=None
    )
    return StationData(messages=messages, last_updated=last_updated)


def top_messages(messages: List[TrainMessage], limit: int) -> List[TrainMessage]:
    return messages[: max(0, limit)]


__all__ = [
    "TrainMessage",
    "StationData",
    "parse_station_data",
    "parse_line_colors",
    "parse_last_updated",
    "top_messages",
]

