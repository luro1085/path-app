from datetime import datetime, timezone

import pytest

import path_app.path_data as path_data
from path_app.path_data import (
    parse_line_colors,
    parse_station_data,
    parse_station_data_with_presumed,
)


def test_parse_line_colors_handles_multi() -> None:
    colors = parse_line_colors("4D92FB,FF9900")
    assert colors == ["#4D92FB", "#FF9900"]


def test_parse_station_data_sorts_and_tracks_latest() -> None:
    payload = {
        "results": [
            {
                "consideredStation": "HOB",
                "destinations": [
                    {
                        "label": "ToNY",
                        "messages": [
                            {
                                "target": "33S",
                                "secondsToArrival": "300",
                                "arrivalTimeMessage": "5 min",
                                "lineColor": "4D92FB,FF9900",
                                "headSign": "33rd Street",
                                "lastUpdated": "2024-01-01T12:00:00-05:00",
                            },
                            {
                                "target": "WTC",
                                "secondsToArrival": "120",
                                "arrivalTimeMessage": "2 min",
                                "lineColor": "4D92FB",
                                "headSign": "World Trade Center",
                                "lastUpdated": "2024-01-01T12:01:00-05:00",
                            },
                        ],
                    }
                ],
            }
        ]
    }
    data = parse_station_data(payload, "HOB")
    assert len(data.messages) == 2
    assert [m.seconds_to_arrival for m in data.messages] == [0, 180]
    assert data.messages[0].headsign == "World Trade Center"
    assert data.last_updated
    assert data.last_updated.tzinfo is not None
    assert data.last_updated == datetime(2024, 1, 1, 17, 1, tzinfo=timezone.utc)


def test_parse_station_data_filters_short_and_offsets_arrivals() -> None:
    payload = {
        "results": [
            {
                "consideredStation": "HOB",
                "destinations": [
                    {
                        "label": "ToJournalSquare",
                        "messages": [
                            {
                                "target": "JSQ",
                                "secondsToArrival": "80",
                                "arrivalTimeMessage": "1 min",
                                "lineColor": "4D92FB",
                                "headSign": "Journal Square",
                                "lastUpdated": "2024-01-01T12:00:00-05:00",
                            },
                            {
                                "target": "JSQ",
                                "secondsToArrival": "200",
                                "arrivalTimeMessage": "3 min",
                                "lineColor": "4D92FB",
                                "headSign": "Journal Square",
                                "lastUpdated": "2024-01-01T12:03:00-05:00",
                            },
                            {
                                "target": "NWK",
                                "secondsToArrival": "400",
                                "arrivalTimeMessage": "Boarding",
                                "lineColor": "FF9900",
                                "headSign": "Newark",
                                "lastUpdated": "2024-01-01T12:05:00-05:00",
                            },
                        ],
                    }
                ],
            }
        ]
    }
    data = parse_station_data(payload, "HOB")
    assert [m.target for m in data.messages] == ["JSQ", "NWK"]
    assert [m.seconds_to_arrival for m in data.messages] == [80, 280]
    assert data.messages[0].arrival_message == "1 min"
    assert data.messages[1].arrival_message == "Boarding"


def test_parse_station_data_handles_missing_station() -> None:
    payload = {"results": []}
    data = parse_station_data(payload, "HOB")
    assert data.messages == []
    assert data.last_updated is None


def test_presumed_hoboken_trains_backfill_from_christopher() -> None:
    raw_chr_seconds = 600
    payload = {
        "results": [
            {
                "consideredStation": "HOB",
                "destinations": [],
            },
            {
                "consideredStation": "CHR",
                "destinations": [
                    {
                        "label": "ToNJ",
                        "messages": [
                            {
                                "target": "JSQ",
                                "secondsToArrival": str(raw_chr_seconds),
                                "arrivalTimeMessage": "10 min",
                                "lineColor": "4D92FB,FF9900",
                                "headSign": "Journal Square via Hoboken",
                                "lastUpdated": "2024-01-01T12:00:00-05:00",
                            }
                        ],
                    }
                ],
            },
        ]
    }
    data = parse_station_data_with_presumed(payload, "HOB", include_presumed=True)
    assert len(data.messages) == 1
    msg = data.messages[0]
    expected_seconds = (
        max(0, raw_chr_seconds - path_data.ARRIVAL_LEAD_SECONDS)
        + path_data.HOBOKEN_FROM_CHRISTOPHER_SECONDS
    )
    assert msg.seconds_to_arrival == expected_seconds
    assert msg.arrival_message.startswith("~")
    assert msg.backfill_source is not None
    assert msg.backfill_source.station_code == "CHR"


def test_presumed_hoboken_trains_dedupes_when_live_exists() -> None:
    raw_chr_seconds = 600
    raw_hob_seconds = raw_chr_seconds + path_data.HOBOKEN_FROM_CHRISTOPHER_SECONDS
    payload = {
        "results": [
            {
                "consideredStation": "HOB",
                "destinations": [
                    {
                        "label": "ToNJ",
                        "messages": [
                            {
                                "target": "JSQ",
                                "secondsToArrival": str(raw_hob_seconds),
                                "arrivalTimeMessage": "25 min",
                                "lineColor": "4D92FB,FF9900",
                                "headSign": "Journal Square via Hoboken",
                                "lastUpdated": "2024-01-01T12:00:00-05:00",
                            }
                        ],
                    }
                ],
            },
            {
                "consideredStation": "CHR",
                "destinations": [
                    {
                        "label": "ToNJ",
                        "messages": [
                            {
                                "target": "JSQ",
                                "secondsToArrival": str(raw_chr_seconds),
                                "arrivalTimeMessage": "10 min",
                                "lineColor": "4D92FB,FF9900",
                                "headSign": "Journal Square via Hoboken",
                                "lastUpdated": "2024-01-01T12:00:00-05:00",
                            }
                        ],
                    }
                ],
            },
        ]
    }
    data = parse_station_data_with_presumed(payload, "HOB", include_presumed=True)
    assert len(data.messages) == 1
    assert data.messages[0].backfill_source is None


# ---------------------------------------------------------------------------
# Headsign-based backfill filtering tests
# ---------------------------------------------------------------------------

def test_direct_jsq_train_not_backfilled_to_hoboken() -> None:
    """A direct JSQ train at CHR (no 'via Hoboken') must not appear at Hoboken."""
    payload = {
        "results": [
            {"consideredStation": "HOB", "destinations": []},
            {
                "consideredStation": "CHR",
                "destinations": [
                    {
                        "label": "ToNJ",
                        "messages": [
                            {
                                "target": "JSQ",
                                "secondsToArrival": "600",
                                "arrivalTimeMessage": "10 min",
                                "lineColor": "4D92FB",
                                "headSign": "Journal Square",
                                "lastUpdated": "2024-01-01T12:00:00-05:00",
                            }
                        ],
                    }
                ],
            },
        ]
    }
    data = parse_station_data_with_presumed(payload, "HOB", include_presumed=True)
    assert len(data.messages) == 0


def test_mixed_direct_and_via_hoboken_at_chr() -> None:
    """Only the via-Hoboken train should be backfilled; the direct one should not."""
    payload = {
        "results": [
            {"consideredStation": "HOB", "destinations": []},
            {
                "consideredStation": "CHR",
                "destinations": [
                    {
                        "label": "ToNJ",
                        "messages": [
                            {
                                "target": "JSQ",
                                "secondsToArrival": "600",
                                "arrivalTimeMessage": "10 min",
                                "lineColor": "4D92FB",
                                "headSign": "Journal Square",
                                "lastUpdated": "2024-01-01T12:00:00-05:00",
                            },
                            {
                                "target": "JSQ",
                                "secondsToArrival": "1200",
                                "arrivalTimeMessage": "20 min",
                                "lineColor": "4D92FB,FF9900",
                                "headSign": "Journal Square via Hoboken",
                                "lastUpdated": "2024-01-01T12:00:00-05:00",
                            },
                        ],
                    }
                ],
            },
        ]
    }
    data = parse_station_data_with_presumed(payload, "HOB", include_presumed=True)
    assert len(data.messages) == 1
    assert "via Hoboken" in data.messages[0].headsign
    assert data.messages[0].backfill_source is not None


def test_future_weekend_hob_wtc_with_direct_jsq_at_chr() -> None:
    """Simulate post-May 2026 Saturday afternoon: HOB has WTC + 33S + direct JSQ
    service, and CHR has direct JSQ trains (no 'via Hoboken' during daytime).

    Expected: HOB shows its own live WTC/33S/JSQ trains. No phantom backfill
    trains are created from CHR because the direct JSQ trains don't route
    through Hoboken.
    """
    payload = {
        "results": [
            {
                "consideredStation": "HOB",
                "destinations": [
                    {
                        # NEW: Weekend HOB-WTC service (every 20 min, 10 AM–9 PM)
                        "label": "ToNY",
                        "messages": [
                            {
                                "target": "WTC",
                                "secondsToArrival": "480",
                                "arrivalTimeMessage": "8 min",
                                "lineColor": "65C100",
                                "headSign": "World Trade Center",
                                "lastUpdated": "2026-05-16T14:00:00-04:00",
                            },
                            {
                                "target": "WTC",
                                "secondsToArrival": "1680",
                                "arrivalTimeMessage": "28 min",
                                "lineColor": "65C100",
                                "headSign": "World Trade Center",
                                "lastUpdated": "2026-05-16T14:00:00-04:00",
                            },
                        ],
                    },
                    {
                        # Weekend HOB-33S service (every 10 min)
                        "label": "ToNY",
                        "messages": [
                            {
                                "target": "33S",
                                "secondsToArrival": "300",
                                "arrivalTimeMessage": "5 min",
                                "lineColor": "4D92FB",
                                "headSign": "33rd Street",
                                "lastUpdated": "2026-05-16T14:00:00-04:00",
                            },
                        ],
                    },
                ],
            },
            {
                # CHR shows DIRECT JSQ trains (no "via Hoboken" during daytime)
                "consideredStation": "CHR",
                "destinations": [
                    {
                        "label": "ToNJ",
                        "messages": [
                            {
                                "target": "JSQ",
                                "secondsToArrival": "300",
                                "arrivalTimeMessage": "5 min",
                                "lineColor": "4D92FB",
                                "headSign": "Journal Square",
                                "lastUpdated": "2026-05-16T14:00:00-04:00",
                            },
                            {
                                "target": "JSQ",
                                "secondsToArrival": "900",
                                "arrivalTimeMessage": "15 min",
                                "lineColor": "4D92FB",
                                "headSign": "Journal Square",
                                "lastUpdated": "2026-05-16T14:00:00-04:00",
                            },
                        ],
                    }
                ],
            },
        ]
    }
    data = parse_station_data_with_presumed(payload, "HOB", include_presumed=True)

    # Should have exactly the 3 live HOB trains — no phantom backfills from CHR
    assert len(data.messages) == 3
    assert all(msg.backfill_source is None for msg in data.messages)

    # Verify the WTC trains are present (the new weekend service)
    wtc_trains = [m for m in data.messages if m.target == "WTC"]
    assert len(wtc_trains) == 2
    assert wtc_trains[0].headsign == "World Trade Center"


def test_future_weekend_night_still_backfills_via_hoboken() -> None:
    """Simulate post-May 2026 Saturday late night: JSQ-33 via Hoboken resumes,
    CHR shows 'via Hoboken' headsign. Backfill should still work.
    """
    payload = {
        "results": [
            {
                "consideredStation": "HOB",
                "destinations": [],
            },
            {
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
                                "lastUpdated": "2026-05-16T23:30:00-04:00",
                            }
                        ],
                    }
                ],
            },
        ]
    }
    data = parse_station_data_with_presumed(payload, "HOB", include_presumed=True)
    assert len(data.messages) == 1
    assert data.messages[0].backfill_source is not None
    assert data.messages[0].backfill_source.station_code == "CHR"


def test_ny_bound_via_hoboken_not_backfilled() -> None:
    """A NY-bound '33rd Street via Hoboken' train at CHR has already passed
    Hoboken and is heading away from it — must NOT be backfilled."""
    payload = {
        "results": [
            {"consideredStation": "HOB", "destinations": []},
            {
                "consideredStation": "CHR",
                "destinations": [
                    {
                        "label": "ToNY",
                        "messages": [
                            {
                                "target": "33S",
                                "secondsToArrival": "600",
                                "arrivalTimeMessage": "10 min",
                                "lineColor": "4D92FB,FF9900",
                                "headSign": "33rd Street via Hoboken",
                                "lastUpdated": "2024-01-01T01:00:00-05:00",
                            }
                        ],
                    }
                ],
            },
        ]
    }
    data = parse_station_data_with_presumed(payload, "HOB", include_presumed=True)
    assert len(data.messages) == 0


def test_via_hoboken_case_insensitive() -> None:
    """Headsign matching should be case-insensitive."""
    payload = {
        "results": [
            {"consideredStation": "HOB", "destinations": []},
            {
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
                                "headSign": "Journal Square VIA HOBOKEN",
                                "lastUpdated": "2024-01-01T12:00:00-05:00",
                            }
                        ],
                    }
                ],
            },
        ]
    }
    data = parse_station_data_with_presumed(payload, "HOB", include_presumed=True)
    assert len(data.messages) == 1
