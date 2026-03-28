from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional


ARRIVAL_LEAD_SECONDS = 120
MIN_SECONDS_TO_SHOW = 90
HOBOKEN_STATION_CODE = "HOB"
CHRISTOPHER_STREET_CODE = "CHR"
JOURNAL_SQUARE_CODE = "JSQ"
HOBOKEN_FROM_CHRISTOPHER_SECONDS = (13 * 60) + 17
STATION_DISPLAY_NAMES: Dict[str, str] = {
    "HOB": "Hoboken",
    "CHR": "Christopher Street",
    "JSQ": "Journal Square",
}


@dataclass
class BackfillSource:
    station_code: str
    station_name: str
    seconds_to_arrival: int
    arrival_message: str


@dataclass
class TrainMessage:
    label: str
    target: str
    seconds_to_arrival: int
    arrival_message: str
    line_colors: List[str]
    headsign: str
    last_updated: Optional[datetime]
    backfill_source: Optional[BackfillSource] = None


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


def station_display_name(station_code: str) -> str:
    return STATION_DISPLAY_NAMES.get(station_code, station_code)


def _format_arrival_message(arrival_message: str, seconds_to_arrival: int) -> str:
    if not arrival_message:
        return ""
    if re.fullmatch(r"\s*(\d+)\s*min\s*", arrival_message, flags=re.IGNORECASE):
        minutes = max(0, seconds_to_arrival // 60)
        return f"{minutes} min"
    return arrival_message


def _find_station_entry(payload: Any, station_code: str) -> Optional[dict]:
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        return None
    return next(
        (entry for entry in results if entry.get("consideredStation") == station_code),
        None,
    )


def _format_relative_minutes(seconds_to_arrival: int) -> str:
    minutes = max(0, seconds_to_arrival // 60)
    return f"{minutes} min"


def _parse_station_messages(
    station_entry: dict, *, min_seconds_to_show: int = MIN_SECONDS_TO_SHOW
) -> List[TrainMessage]:
    messages: List[TrainMessage] = []
    for destination in station_entry.get("destinations", []):
        label = destination.get("label", "")
        for raw_msg in destination.get("messages", []):
            try:
                raw_seconds = int(raw_msg.get("secondsToArrival", "0"))
            except (TypeError, ValueError):
                continue
            if raw_seconds < min_seconds_to_show:
                continue
            seconds = max(0, raw_seconds - ARRIVAL_LEAD_SECONDS)
            arrival_message = str(raw_msg.get("arrivalTimeMessage", "")).strip()
            arrival_message = _format_arrival_message(arrival_message, seconds)
            message = TrainMessage(
                label=label,
                target=str(raw_msg.get("target", "")).strip(),
                seconds_to_arrival=seconds,
                arrival_message=arrival_message,
                line_colors=parse_line_colors(str(raw_msg.get("lineColor", ""))),
                headsign=str(raw_msg.get("headSign", "")).strip(),
                last_updated=parse_last_updated(raw_msg.get("lastUpdated")),
            )
            messages.append(message)

    messages.sort(key=lambda m: m.seconds_to_arrival)
    return messages


def _latest_update(messages: List[TrainMessage]) -> Optional[datetime]:
    return max((msg.last_updated for msg in messages if msg.last_updated), default=None)


def _is_journal_square_train(message: TrainMessage) -> bool:
    target = message.target.strip().upper()
    headsign = message.headsign.strip().upper()
    return (
        target == JOURNAL_SQUARE_CODE
        or "JOURNAL" in headsign
        or "JSQ" in headsign
    )


def _is_via_hoboken_to_jsq(message: TrainMessage) -> bool:
    """Return True if the train is NJ-bound on the via-Hoboken line toward JSQ.

    Must be both:
    - on the via-Hoboken route (headsign contains "via Hoboken")
    - heading toward Journal Square (NJ-bound)

    This excludes NY-bound "33rd Street via Hoboken" trains at Christopher St
    that have already passed through Hoboken and are heading away from it.
    """
    return "via hoboken" in message.headsign.lower() and _is_journal_square_train(message)


def _get_close_train_threshold_seconds(now: Optional[datetime] = None) -> int:
    local_now = (now or datetime.now().astimezone())
    if local_now.weekday() >= 5:
        return 10 * 60
    if 6 <= local_now.hour <= 10 or 16 <= local_now.hour <= 20:
        return 4 * 60
    return 10 * 60


def _has_close_match(
    messages: List[TrainMessage], seconds_to_arrival: int
) -> bool:
    threshold = _get_close_train_threshold_seconds()
    for existing in messages:
        if not _is_journal_square_train(existing):
            continue
        if abs(existing.seconds_to_arrival - seconds_to_arrival) <= threshold:
            return True
    return False


def _build_hoboken_presumed_trains(
    payload: Any, existing_messages: List[TrainMessage]
) -> List[TrainMessage]:
    source_entry = _find_station_entry(payload, CHRISTOPHER_STREET_CODE)
    if not source_entry:
        return []

    presumed_messages: List[TrainMessage] = []
    source_messages = _parse_station_messages(source_entry, min_seconds_to_show=0)
    for source in source_messages:
        if not _is_via_hoboken_to_jsq(source):
            continue
        seconds_to_arrival = source.seconds_to_arrival + HOBOKEN_FROM_CHRISTOPHER_SECONDS
        if seconds_to_arrival < MIN_SECONDS_TO_SHOW:
            continue
        if _has_close_match(existing_messages + presumed_messages, seconds_to_arrival):
            continue

        presumed_messages.append(
            TrainMessage(
                label=source.label,
                target=source.target or JOURNAL_SQUARE_CODE,
                seconds_to_arrival=seconds_to_arrival,
                arrival_message=f"~{max(0, seconds_to_arrival // 60)} min",
                line_colors=source.line_colors,
                headsign=source.headsign or STATION_DISPLAY_NAMES[JOURNAL_SQUARE_CODE],
                last_updated=source.last_updated,
                backfill_source=BackfillSource(
                    station_code=CHRISTOPHER_STREET_CODE,
                    station_name=station_display_name(CHRISTOPHER_STREET_CODE),
                    seconds_to_arrival=source.seconds_to_arrival,
                    arrival_message=_format_relative_minutes(source.seconds_to_arrival),
                ),
            )
        )

    return presumed_messages


def build_presumed_tooltip(message: TrainMessage, station_code: str) -> str:
    if not message.backfill_source:
        return ""
    station_name = station_display_name(station_code)
    train_title = message.headsign or message.target
    train_title = train_title.split(" via", 1)[0].split(" VIA", 1)[0]
    source_time = (
        message.backfill_source.arrival_message
        or _format_relative_minutes(message.backfill_source.seconds_to_arrival)
    )
    return (
        f"This train is not yet reported for {station_name} by PATH, "
        f"but is displayed here because a train to {train_title} is departing "
        f"from {message.backfill_source.station_name} in {source_time}."
    )


# DEPRECATED: Time-based gating replaced by headsign-based filtering in
# _is_via_hoboken_train().  The API headsign ("via Hoboken") is the source of
# truth for whether a train routes through Hoboken, making this function
# unnecessary and schedule-change-proof.
def is_presumed_service_active(dt: datetime) -> bool:
    """Return True when the JSQ-via-Hoboken service runs through Christopher Street.

    .. deprecated::
        No longer used as a gate.  Headsign filtering in
        ``_build_hoboken_presumed_trains`` handles this automatically.
    """
    import os
    if os.getenv("PATH_FAKE_SCHEDULE") == "weekend":
        return True
    if dt.weekday() >= 5:  # Saturday=5, Sunday=6
        return True
    return dt.hour >= 23 or dt.hour < 6


def parse_station_data(payload: Any, station_code: str) -> StationData:
    station_entry = _find_station_entry(payload, station_code)
    if not station_entry:
        return StationData(messages=[], last_updated=None)

    messages = _parse_station_messages(station_entry)
    return StationData(messages=messages, last_updated=_latest_update(messages))


def parse_station_data_with_presumed(
    payload: Any, station_code: str, *, include_presumed: bool = True
) -> StationData:
    base_data = parse_station_data(payload, station_code)
    if not include_presumed or station_code != HOBOKEN_STATION_CODE:
        return base_data

    presumed_messages = _build_hoboken_presumed_trains(payload, base_data.messages)
    if not presumed_messages:
        return base_data

    merged = list(base_data.messages) + presumed_messages
    merged.sort(key=lambda m: m.seconds_to_arrival)
    return StationData(messages=merged, last_updated=_latest_update(merged))


def top_messages(messages: List[TrainMessage], limit: int) -> List[TrainMessage]:
    return messages[: max(0, limit)]


__all__ = [
    "BackfillSource",
    "TrainMessage",
    "StationData",
    "build_presumed_tooltip",
    "parse_station_data",
    "parse_station_data_with_presumed",
    "parse_line_colors",
    "parse_last_updated",
    "station_display_name",
    "top_messages",
]
