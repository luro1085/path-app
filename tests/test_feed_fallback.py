from datetime import datetime, timedelta, timezone

import pytest

from path_app.app import FetchThread
from path_app.config import DEFAULT_CONFIG, load_config
from path_app.path_data import ridepath_has_departures


RIDEPATH_OK = {
    "results": [
        {
            "consideredStation": "HOB",
            "destinations": [
                {
                    "label": "ToNY",
                    "messages": [
                        {
                            "target": "WTC",
                            "secondsToArrival": "600",
                            "arrivalTimeMessage": "10 min",
                            "lineColor": "65C100",
                            "headSign": "World Trade Center",
                            "lastUpdated": "2026-11-17T18:00:00-05:00",
                        }
                    ],
                }
            ],
        }
    ]
}
RIDEPATH_EMPTY = {"results": []}
RIDEPATH_NO_MESSAGES = {
    "results": [{"consideredStation": "HOB", "destinations": [{"label": "ToNY", "messages": []}]}]
}


def _citymapper_payload() -> dict:
    now = datetime.now(timezone.utc)
    return {
        "stations": [
            {
                "station": {"live_code": "PATHHoboken"},
                "sections": [
                    {
                        "departure_groupings": [
                            {
                                "departures": [
                                    {
                                        "destination_name": "33rd Street",
                                        "route_id": "PATHHob33",
                                        "scheduled_time": (now + timedelta(minutes=10)).isoformat(),
                                    }
                                ]
                            }
                        ]
                    }
                ],
                "routes": [
                    {
                        "live_line_code": "PATHHob33",
                        "color": "#4d92fb",
                        "long_name": "Hoboken-33rd Street",
                    }
                ],
            }
        ],
        "last_updated_time": now.isoformat(),
    }


@pytest.fixture
def thread(tmp_path, monkeypatch):
    monkeypatch.delenv("PATH_FAKE_FEED", raising=False)
    monkeypatch.delenv("PATH_FORCE_CITYMAPPER", raising=False)
    config = load_config(tmp_path / "config.json")
    assert config.station == DEFAULT_CONFIG["station"] == "HOB"
    t = FetchThread(config)
    t.citymapper_calls = 0

    def fake_citymapper():
        t.citymapper_calls += 1
        return _citymapper_payload()

    t._fetch_citymapper = fake_citymapper
    yield t
    t.session.close()


def test_ridepath_used_when_it_has_departures(thread) -> None:
    thread._fetch_ridepath = lambda: RIDEPATH_OK
    data = thread._fetch_once()
    assert [m.headsign for m in data.messages] == ["World Trade Center"]
    assert thread.citymapper_calls == 0
    assert thread._source == "ridepath"


@pytest.mark.parametrize("payload", [RIDEPATH_EMPTY, RIDEPATH_NO_MESSAGES])
def test_citymapper_used_when_ridepath_lists_no_trains(thread, payload) -> None:
    thread._fetch_ridepath = lambda: payload
    data = thread._fetch_once()
    assert [m.headsign for m in data.messages] == ["33rd Street"]
    assert thread.citymapper_calls == 1
    assert thread._source == "citymapper"


def test_citymapper_used_when_ridepath_errors(thread) -> None:
    def boom():
        raise TimeoutError("Read timed out")

    thread._fetch_ridepath = boom
    data = thread._fetch_once()
    assert [m.headsign for m in data.messages] == ["33rd Street"]
    assert thread._source == "citymapper"


def test_switches_back_to_ridepath_when_it_recovers(thread) -> None:
    thread._fetch_ridepath = lambda: RIDEPATH_EMPTY
    thread._fetch_once()
    assert thread._source == "citymapper"
    thread._fetch_ridepath = lambda: RIDEPATH_OK
    thread._fetch_once()
    assert thread._source == "ridepath"


def test_raises_when_both_feeds_fail(thread) -> None:
    def ridepath_boom():
        raise TimeoutError("ridepath down")

    def citymapper_boom():
        raise ConnectionError("citymapper down")

    thread._fetch_ridepath = ridepath_boom
    thread._fetch_citymapper = citymapper_boom
    with pytest.raises(RuntimeError) as excinfo:
        thread._fetch_once()
    assert "ridepath down" in str(excinfo.value)
    assert "citymapper down" in str(excinfo.value)


def test_force_citymapper_skips_ridepath(thread, monkeypatch) -> None:
    monkeypatch.setenv("PATH_FORCE_CITYMAPPER", "1")

    def should_not_run():
        raise AssertionError("ridepath should be skipped")

    thread._fetch_ridepath = should_not_run
    data = thread._fetch_once()
    assert [m.headsign for m in data.messages] == ["33rd Street"]


def test_ridepath_has_departures() -> None:
    assert ridepath_has_departures(RIDEPATH_OK, "HOB")
    assert not ridepath_has_departures(RIDEPATH_OK, "CHR")
    assert not ridepath_has_departures(RIDEPATH_EMPTY, "HOB")
    assert not ridepath_has_departures(RIDEPATH_NO_MESSAGES, "HOB")
    assert not ridepath_has_departures({"error": "x"}, "HOB")
    assert not ridepath_has_departures(None, "HOB")
