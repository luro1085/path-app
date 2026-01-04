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
    assert [m.seconds_to_arrival for m in data.messages] == [30, 210]
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
    assert [m.seconds_to_arrival for m in data.messages] == [110, 310]
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
    assert msg.arrival_message.startswith("est ")
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
