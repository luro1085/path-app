from datetime import datetime, timedelta, timezone

import path_app.path_data as path_data
from path_app.path_data import (
    parse_line_colors,
    parse_station_data,
    parse_station_data_with_presumed,
)

NOW = datetime(2026, 11, 17, 22, 30, tzinfo=timezone.utc)
LEAD = path_data.ARRIVAL_LEAD_SECONDS

ROUTES = {
    "PATHHob33": ("#4d92fb", "Hoboken-33rd Street"),
    "PATHHobwtc": ("#65c100", "Hoboken-World Trade Center"),
    "PATHJsq33": ("#ff9900", "Journal Square-33rd Street"),
    "PATHJsqhob33": ("#ff9900", "Journal Square-33rd Street (Via Hoboken)"),
}


def _dep(destination, route_id, *, scheduled_in=None, live_in=None):
    dep = {"destination_name": destination, "route_id": route_id, "direction_id": "1"}
    if scheduled_in is not None:
        dep["scheduled_time"] = (NOW + timedelta(seconds=scheduled_in)).isoformat()
    if live_in is not None:
        dep["time_seconds"] = live_in
    return dep


def _station(live_code, departures):
    route_ids = sorted({d["route_id"] for d in departures})
    return {
        "station": {"name": live_code, "live_code": live_code},
        "messages": [],
        "sections": [
            {"id": live_code, "departure_groupings": [{"departures": departures}]}
        ],
        "routes": [
            {
                "live_line_code": rid,
                "color": ROUTES[rid][0],
                "long_name": ROUTES[rid][1],
            }
            for rid in route_ids
        ],
    }


def _payload(hob=None, chr_=None, *, updated=NOW):
    stations = []
    if hob is not None:
        stations.append(_station("PATHHoboken", hob))
    if chr_ is not None:
        stations.append(_station("PATHChristopherSt", chr_))
    return {"stations": stations, "last_updated_time": updated.isoformat()}


def test_parse_line_colors_handles_multi() -> None:
    colors = parse_line_colors("4D92FB,FF9900")
    assert colors == ["#4D92FB", "#FF9900"]


def test_parse_station_data_sorts_and_tracks_latest() -> None:
    payload = _payload(
        [
            _dep("33rd Street", "PATHHob33", scheduled_in=300 + LEAD),
            _dep("World Trade Center", "PATHHobwtc", scheduled_in=120 + LEAD),
        ]
    )
    data = parse_station_data(payload, "HOB", now=NOW)
    assert [m.seconds_to_arrival for m in data.messages] == [120, 300]
    first = data.messages[0]
    assert first.headsign == "World Trade Center"
    assert first.target == "WTC"
    assert first.label == "ToNY"
    assert first.arrival_message == "2 min"
    assert first.line_colors == ["#65C100"]
    assert data.last_updated == NOW


def test_live_countdown_preferred_and_relative_to_last_updated() -> None:
    # Feed was generated 30s before "now"; countdown is relative to that.
    payload = _payload(
        [_dep("33rd Street", "PATHHob33", scheduled_in=900, live_in=330 + LEAD)],
        updated=NOW - timedelta(seconds=30),
    )
    data = parse_station_data(payload, "HOB", now=NOW)
    assert [m.seconds_to_arrival for m in data.messages] == [300]
    assert data.messages[0].arrival_message == "5 min"


def test_parse_station_data_drops_departed_and_advisories() -> None:
    payload = _payload(
        [
            _dep("Journal Square", "PATHJsq33", scheduled_in=-20),
            _dep("Journal Square", "PATHJsq33", live_in=path_data.MIN_SECONDS_TO_SHOW - 1),
            _dep("Journal Square", "PATHJsq33", live_in=LEAD + 30),
            {
                "route_id": "PATHJsqhob33",
                "destination_name": "No current departures",
                "is_advisory_message": 1,
            },
        ]
    )
    data = parse_station_data(payload, "HOB", now=NOW)
    assert len(data.messages) == 1
    assert data.messages[0].seconds_to_arrival == 30
    assert data.messages[0].arrival_message == "0 min"
    assert data.messages[0].label == "ToNJ"


def test_parse_station_data_handles_missing_station() -> None:
    data = parse_station_data({"stations": []}, "HOB", now=NOW)
    assert data.messages == []
    assert data.last_updated is None
    assert parse_station_data({"error": "Unknown stations."}, "HOB").messages == []


def test_via_hoboken_route_gets_headsign_and_blended_colors() -> None:
    payload = _payload(
        [
            _dep("Journal Square", "PATHJsqhob33", scheduled_in=300),
            _dep("33rd Street", "PATHJsqhob33", scheduled_in=400),
        ]
    )
    data = parse_station_data(payload, "HOB", now=NOW)
    assert [m.headsign for m in data.messages] == [
        "Journal Square via Hoboken",
        "33rd Street via Hoboken",
    ]
    assert [m.label for m in data.messages] == ["ToNJ", "ToNY"]
    assert all(m.line_colors == ["#4D92FB", "#FF9900"] for m in data.messages)


def test_presumed_hoboken_trains_backfill_from_christopher() -> None:
    chr_seconds = 600
    payload = _payload(
        [], [_dep("Journal Square", "PATHJsqhob33", scheduled_in=chr_seconds)]
    )
    data = parse_station_data_with_presumed(payload, "HOB", include_presumed=True, now=NOW)
    assert len(data.messages) == 1
    msg = data.messages[0]
    assert msg.seconds_to_arrival == (
        chr_seconds - LEAD + path_data.HOBOKEN_FROM_CHRISTOPHER_SECONDS
    )
    assert msg.arrival_message.startswith("~")
    assert msg.backfill_source is not None
    assert msg.backfill_source.station_code == "CHR"


def test_presumed_hoboken_trains_dedupes_when_live_exists() -> None:
    chr_seconds = 600
    hob_seconds = chr_seconds + path_data.HOBOKEN_FROM_CHRISTOPHER_SECONDS
    payload = _payload(
        [_dep("Journal Square", "PATHJsqhob33", scheduled_in=hob_seconds)],
        [_dep("Journal Square", "PATHJsqhob33", scheduled_in=chr_seconds)],
    )
    data = parse_station_data_with_presumed(payload, "HOB", include_presumed=True, now=NOW)
    assert len(data.messages) == 1
    assert data.messages[0].backfill_source is None


def test_presumed_disabled_or_other_station() -> None:
    payload = _payload(
        [], [_dep("Journal Square", "PATHJsqhob33", scheduled_in=600)]
    )
    assert parse_station_data_with_presumed(
        payload, "HOB", include_presumed=False, now=NOW
    ).messages == []


# ---------------------------------------------------------------------------
# Route-based backfill filtering tests
# ---------------------------------------------------------------------------

def test_direct_jsq_train_not_backfilled_to_hoboken() -> None:
    """A direct JSQ-33 train at CHR must not appear at Hoboken."""
    payload = _payload([], [_dep("Journal Square", "PATHJsq33", scheduled_in=600)])
    data = parse_station_data_with_presumed(payload, "HOB", include_presumed=True, now=NOW)
    assert data.messages == []


def test_hob33_train_to_hoboken_not_backfilled() -> None:
    """An HOB-33 train at CHR heading to Hoboken is not a JSQ train."""
    payload = _payload([], [_dep("Hoboken", "PATHHob33", scheduled_in=600)])
    data = parse_station_data_with_presumed(payload, "HOB", include_presumed=True, now=NOW)
    assert data.messages == []


def test_mixed_direct_and_via_hoboken_at_chr() -> None:
    payload = _payload(
        [],
        [
            _dep("Journal Square", "PATHJsq33", scheduled_in=600),
            _dep("Journal Square", "PATHJsqhob33", scheduled_in=1200),
        ],
    )
    data = parse_station_data_with_presumed(payload, "HOB", include_presumed=True, now=NOW)
    assert len(data.messages) == 1
    assert "via Hoboken" in data.messages[0].headsign
    assert data.messages[0].backfill_source is not None


def test_weekend_day_hob_wtc_with_direct_jsq_at_chr() -> None:
    """HOB has WTC + 33S service and CHR has direct JSQ trains: HOB shows only
    its own trains, with no phantom backfills."""
    payload = _payload(
        [
            _dep("World Trade Center", "PATHHobwtc", scheduled_in=480),
            _dep("World Trade Center", "PATHHobwtc", scheduled_in=1680),
            _dep("33rd Street", "PATHHob33", scheduled_in=300),
        ],
        [
            _dep("Journal Square", "PATHJsq33", scheduled_in=300),
            _dep("Journal Square", "PATHJsq33", scheduled_in=900),
        ],
    )
    data = parse_station_data_with_presumed(payload, "HOB", include_presumed=True, now=NOW)
    assert len(data.messages) == 3
    assert all(msg.backfill_source is None for msg in data.messages)
    assert len([m for m in data.messages if m.target == "WTC"]) == 2


def test_ny_bound_via_hoboken_not_backfilled() -> None:
    """A NY-bound '33rd Street via Hoboken' train at CHR has already passed
    Hoboken — must NOT be backfilled."""
    payload = _payload([], [_dep("33rd Street", "PATHJsqhob33", scheduled_in=600)])
    data = parse_station_data_with_presumed(payload, "HOB", include_presumed=True, now=NOW)
    assert data.messages == []
