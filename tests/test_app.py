from path_app.board_format import (
    GRID_COLS,
    build_board_rows,
    build_train_row_colors,
    compact_arrival_text,
    format_train_row,
    has_delayed_visible_trains,
)
from path_app.path_data import TrainMessage


def _make_message(
    headsign: str,
    arrival_message: str,
    *,
    backfill_source=None,
) -> TrainMessage:
    return TrainMessage(
        label="ToNY",
        target="WTC",
        seconds_to_arrival=600,
        arrival_message=arrival_message,
        line_colors=["#FFFFFF"],
        headsign=headsign,
        last_updated=None,
        backfill_source=backfill_source,
    )


def test_compact_arrival_text_formats_minutes_boarding_and_status() -> None:
    assert compact_arrival_text("12 min") == "12MIN"
    assert compact_arrival_text("~8 min") == "~8MIN"
    assert compact_arrival_text("8 min", is_presumed=True) == "~8MIN"
    assert compact_arrival_text("0 min") == "DUE"
    assert compact_arrival_text("Boarding") == "BOARD"
    assert compact_arrival_text("Delayed") == "DELAY"


def test_format_train_row_fits_longest_supported_strings() -> None:
    row = format_train_row(_make_message("World Trade Center", "12 min"))

    assert row == "WORLD TRADE    12MIN"
    assert len(row) == GRID_COLS


def test_format_train_row_compacts_presumed_trains_without_double_tilde() -> None:
    row = format_train_row(
        _make_message(
            "Journal Square via Hoboken",
            "~10 min",
            backfill_source=object(),
        )
    )

    assert row == "JOURNAL SQ    ~10MIN"
    assert len(row) == GRID_COLS


def test_build_board_rows_centers_empty_state_on_twenty_column_board() -> None:
    rows = build_board_rows([], max_cards=5)

    assert len(rows) == 5
    assert rows[2]["text"] == "  NO TRAINS POSTED  "
    assert len(rows[2]["text"]) == GRID_COLS


def test_build_board_rows_limits_visible_trains_but_keeps_five_slots() -> None:
    rows = build_board_rows(
        [
            _make_message("World Trade Center", "1 min"),
            _make_message("Journal Square", "2 min"),
            _make_message("33rd Street", "3 min"),
            _make_message("Newark", "4 min"),
            _make_message("Hoboken", "5 min"),
        ],
        max_cards=3,
    )

    assert len(rows) == 5
    assert rows[0]["text"].startswith("WORLD TRADE")
    assert rows[0]["text"].endswith("1MIN")
    assert len(rows[0]["text"]) == GRID_COLS
    assert rows[1]["text"].startswith("JOURNAL SQ")
    assert rows[1]["text"].endswith("2MIN")
    assert len(rows[1]["text"]) == GRID_COLS
    assert rows[2]["text"].startswith("33RD ST")
    assert rows[2]["text"].endswith("3MIN")
    assert len(rows[2]["text"]) == GRID_COLS
    assert rows[3]["text"] == ""
    assert rows[4]["text"] == ""


def test_build_board_rows_clamps_capacity_to_five_departures() -> None:
    rows = build_board_rows(
        [
            _make_message("World Trade Center", "1 min"),
            _make_message("Journal Square", "2 min"),
            _make_message("33rd Street", "3 min"),
            _make_message("Newark", "4 min"),
            _make_message("Hoboken", "5 min"),
            _make_message("Christopher Street", "6 min"),
        ],
        max_cards=99,
    )

    assert len(rows) == 5
    assert rows[-1]["text"].startswith("HOBOKEN")
    assert rows[-1]["text"].endswith("5MIN")
    assert len(rows[-1]["text"]) == GRID_COLS


def test_build_train_row_colors_inverts_only_eta_digits() -> None:
    message = _make_message("World Trade Center", "12 min")
    row = format_train_row(message)
    colors = build_train_row_colors(message, row)
    time_start = len(row) - len("12MIN")

    assert len(colors) == GRID_COLS
    assert colors[time_start] == {"fg": "#FFFFFF", "bg": "#FFFFFF"}
    assert colors[time_start + 1] == {"fg": "#FFFFFF", "bg": "#FFFFFF"}
    assert colors[time_start + 2] == "#FFFFFF"
    assert colors[time_start + 3] == "#FFFFFF"
    assert colors[time_start + 4] == "#FFFFFF"


def test_has_delayed_visible_trains_detects_delayed() -> None:
    delayed = _make_message("World Trade Center", "Delayed")
    normal = _make_message("Journal Square", "5 min")
    assert has_delayed_visible_trains([delayed, normal], max_cards=5) is True
    assert has_delayed_visible_trains([normal], max_cards=5) is False


def test_has_delayed_visible_trains_ignores_offscreen() -> None:
    msgs = [_make_message("33rd Street", "1 min")] * 5 + [
        _make_message("Newark", "Delayed")
    ]
    assert has_delayed_visible_trains(msgs, max_cards=5) is False
