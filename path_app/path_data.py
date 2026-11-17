from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from typing import Any, Callable, Dict, Iterator, List, Optional


# --- Primary feed: PATH's ridepath.json -------------------------------------
# The ridepath countdown runs ~2 min long, so shown times are pulled earlier.
ARRIVAL_LEAD_SECONDS = 120
MIN_SECONDS_TO_SHOW = 90

# --- Backup feed: Citymapper metrodepartures --------------------------------
# Citymapper's times line up with scheduled departures, so a smaller lead.
CITYMAPPER_ARRIVAL_LEAD_SECONDS = 60
# Trains whose raw (pre-lead) time is under this are dropped (keeps a train on
# the board as DUE until ~30s before its displayed time would go negative).
CITYMAPPER_MIN_SECONDS_TO_SHOW = 30

HOBOKEN_STATION_CODE = "HOB"
CHRISTOPHER_STREET_CODE = "CHR"
JOURNAL_SQUARE_CODE = "JSQ"
HOBOKEN_FROM_CHRISTOPHER_SECONDS = (13 * 60) + 17
STATION_DISPLAY_NAMES: Dict[str, str] = {
    "HOB": "Hoboken",
    "CHR": "Christopher Street",
    "JSQ": "Journal Square",
}
CITYMAPPER_STATION_IDS: Dict[str, str] = {
    "HOB": "PATHHoboken",
    "CHR": "PATHChristopherSt",
    "JSQ": "PATHJournalSquare",
}
# Citymapper destination name -> PATH target code.
DESTINATION_CODES: Dict[str, str] = {
    "World Trade Center": "WTC",
    "33rd Street": "33S",
    "Journal Square": "JSQ",
    "Hoboken": "HOB",
    "Newark": "NWK",
}
NY_BOUND_DESTINATIONS = {
    "World Trade Center",
    "33rd Street",
    "23rd Street",
    "14th Street",
    "9th Street",
    "Christopher Street",
}
# JSQ-33 via Hoboken is a blended route: blue toward NY, orange toward NJ
# (matching ridepath's "4D92FB,FF9900" lineColor).
VIA_HOBOKEN_LINE_COLORS = ["#4D92FB", "#FF9900"]


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


def _format_relative_minutes(seconds_to_arrival: int) -> str:
    minutes = max(0, seconds_to_arrival // 60)
    return f"{minutes} min"


def _latest_update(messages: List[TrainMessage]) -> Optional[datetime]:
    return max((msg.last_updated for msg in messages if msg.last_updated), default=None)


# ---------------------------------------------------------------------------
# ridepath.json parsing (primary)
# ---------------------------------------------------------------------------

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


def ridepath_has_departures(payload: Any, station_code: str) -> bool:
    """True if ridepath.json lists at least one train for the station.

    Used to decide whether to fall back to Citymapper: an outage has looked
    like an empty/missing station entry rather than an HTTP error.
    """
    station_entry = _find_station_entry(payload, station_code)
    if not station_entry:
        return False
    return any(
        destination.get("messages")
        for destination in station_entry.get("destinations", [])
        if isinstance(destination, dict)
    )


# ---------------------------------------------------------------------------
# Citymapper metrodepartures parsing (backup)
# ---------------------------------------------------------------------------

def citymapper_station_id(station_code: str) -> str:
    return CITYMAPPER_STATION_IDS.get(station_code, station_code)


def _find_citymapper_station_entry(payload: Any, station_code: str) -> Optional[dict]:
    stations = payload.get("stations") if isinstance(payload, dict) else None
    if not isinstance(stations, list):
        return None
    live_code = citymapper_station_id(station_code)
    return next(
        (
            entry
            for entry in stations
            if isinstance(entry, dict)
            and (entry.get("station") or {}).get("live_code") == live_code
        ),
        None,
    )


def _is_via_hoboken_route(route: dict) -> bool:
    return "via hoboken" in str(route.get("long_name", "")).lower()


def _route_line_colors(route: dict) -> List[str]:
    if _is_via_hoboken_route(route):
        return list(VIA_HOBOKEN_LINE_COLORS)
    return parse_line_colors(str(route.get("color", "")))


def _iter_departures(station_entry: dict) -> Iterator[dict]:
    for section in station_entry.get("sections") or []:
        for grouping in (section or {}).get("departure_groupings") or []:
            for departure in (grouping or {}).get("departures") or []:
                if isinstance(departure, dict):
                    yield departure


def _departure_time(departure: dict, reference: datetime) -> Optional[datetime]:
    """Resolve a departure's absolute time.

    Citymapper gives near-term trains a live countdown (``time_seconds``,
    relative to the payload's ``last_updated_time``) and later trains only a
    ``scheduled_time``. Prefer the live countdown when present.
    """
    live_seconds = departure.get("time_seconds")
    if live_seconds is not None:
        try:
            return reference + timedelta(seconds=float(live_seconds))
        except (TypeError, ValueError):
            pass
    return parse_last_updated(departure.get("scheduled_time"))


def _parse_citymapper_station_messages(
    station_entry: dict,
    *,
    now: datetime,
    last_updated: Optional[datetime],
    min_seconds_to_show: int = CITYMAPPER_MIN_SECONDS_TO_SHOW,
) -> List[TrainMessage]:
    routes = {
        route.get("live_line_code"): route
        for route in station_entry.get("routes") or []
        if isinstance(route, dict)
    }
    messages: List[TrainMessage] = []
    for departure in _iter_departures(station_entry):
        if departure.get("is_advisory_message"):
            continue
        departure_time = _departure_time(departure, last_updated or now)
        if departure_time is None:
            continue
        raw_seconds = int((departure_time - now).total_seconds())
        if raw_seconds < min_seconds_to_show:
            continue
        seconds = max(0, raw_seconds - CITYMAPPER_ARRIVAL_LEAD_SECONDS)

        destination = str(departure.get("destination_name", "")).strip()
        route = routes.get(departure.get("route_id"), {})
        headsign = destination
        if _is_via_hoboken_route(route) and destination.lower() != "hoboken":
            headsign = f"{destination} via Hoboken"

        messages.append(
            TrainMessage(
                label="ToNY" if destination in NY_BOUND_DESTINATIONS else "ToNJ",
                target=DESTINATION_CODES.get(destination, destination.upper()),
                seconds_to_arrival=seconds,
                arrival_message=_format_relative_minutes(seconds),
                line_colors=_route_line_colors(route),
                headsign=headsign,
                last_updated=last_updated,
            )
        )

    messages.sort(key=lambda m: m.seconds_to_arrival)
    return messages


def _citymapper_last_updated(payload: Any) -> Optional[datetime]:
    if not isinstance(payload, dict):
        return None
    return parse_last_updated(payload.get("last_updated_time"))


def _resolve_now(now: Optional[datetime]) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now


# ---------------------------------------------------------------------------
# Presumed Hoboken trains (shared by both feeds)
# ---------------------------------------------------------------------------

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


def _presumed_from_christopher(
    source_messages: List[TrainMessage], existing_messages: List[TrainMessage]
) -> List[TrainMessage]:
    presumed_messages: List[TrainMessage] = []
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


def _build_hoboken_presumed_trains(
    payload: Any, existing_messages: List[TrainMessage]
) -> List[TrainMessage]:
    source_entry = _find_station_entry(payload, CHRISTOPHER_STREET_CODE)
    if not source_entry:
        return []
    source_messages = _parse_station_messages(source_entry, min_seconds_to_show=0)
    return _presumed_from_christopher(source_messages, existing_messages)


def _build_citymapper_hoboken_presumed_trains(
    payload: Any, existing_messages: List[TrainMessage], *, now: datetime
) -> List[TrainMessage]:
    source_entry = _find_citymapper_station_entry(payload, CHRISTOPHER_STREET_CODE)
    if not source_entry:
        return []
    source_messages = _parse_citymapper_station_messages(
        source_entry,
        now=now,
        last_updated=_citymapper_last_updated(payload),
        min_seconds_to_show=0,
    )
    return _presumed_from_christopher(source_messages, existing_messages)


def _merge_presumed(
    base_data: StationData,
    station_code: str,
    include_presumed: bool,
    build: Callable[[List[TrainMessage]], List[TrainMessage]],
) -> StationData:
    if not include_presumed or station_code != HOBOKEN_STATION_CODE:
        return base_data

    presumed_messages = build(base_data.messages)
    if not presumed_messages:
        return base_data

    merged = list(base_data.messages) + presumed_messages
    merged.sort(key=lambda m: m.seconds_to_arrival)
    return StationData(messages=merged, last_updated=_latest_update(merged))


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


# ---------------------------------------------------------------------------
# Public parse functions
# ---------------------------------------------------------------------------

def parse_station_data(payload: Any, station_code: str) -> StationData:
    """Parse a ridepath.json payload."""
    station_entry = _find_station_entry(payload, station_code)
    if not station_entry:
        return StationData(messages=[], last_updated=None)

    messages = _parse_station_messages(station_entry)
    return StationData(messages=messages, last_updated=_latest_update(messages))


def parse_station_data_with_presumed(
    payload: Any, station_code: str, *, include_presumed: bool = True
) -> StationData:
    """Parse a ridepath.json payload, adding presumed Hoboken trains."""
    base_data = parse_station_data(payload, station_code)
    return _merge_presumed(
        base_data,
        station_code,
        include_presumed,
        lambda existing: _build_hoboken_presumed_trains(payload, existing),
    )


def parse_citymapper_station_data(
    payload: Any, station_code: str, *, now: Optional[datetime] = None
) -> StationData:
    """Parse a Citymapper metrodepartures payload."""
    station_entry = _find_citymapper_station_entry(payload, station_code)
    if not station_entry:
        return StationData(messages=[], last_updated=None)

    messages = _parse_citymapper_station_messages(
        station_entry,
        now=_resolve_now(now),
        last_updated=_citymapper_last_updated(payload),
    )
    return StationData(messages=messages, last_updated=_latest_update(messages))


def parse_citymapper_station_data_with_presumed(
    payload: Any,
    station_code: str,
    *,
    include_presumed: bool = True,
    now: Optional[datetime] = None,
) -> StationData:
    """Parse a Citymapper metrodepartures payload, adding presumed Hoboken trains."""
    now = _resolve_now(now)
    base_data = parse_citymapper_station_data(payload, station_code, now=now)
    return _merge_presumed(
        base_data,
        station_code,
        include_presumed,
        lambda existing: _build_citymapper_hoboken_presumed_trains(
            payload, existing, now=now
        ),
    )


def top_messages(messages: List[TrainMessage], limit: int) -> List[TrainMessage]:
    return messages[: max(0, limit)]


__all__ = [
    "BackfillSource",
    "TrainMessage",
    "StationData",
    "build_presumed_tooltip",
    "citymapper_station_id",
    "parse_citymapper_station_data",
    "parse_citymapper_station_data_with_presumed",
    "parse_station_data",
    "parse_station_data_with_presumed",
    "parse_line_colors",
    "parse_last_updated",
    "ridepath_has_departures",
    "station_display_name",
    "top_messages",
]
