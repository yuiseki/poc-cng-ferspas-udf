"""Offsets in whole months, and the machinery for reading many frames."""

import numpy as np
import pytest

from ferspas_tile.analysis import Input, shift, shift_months
from ferspas_tile.climatology import (
    monthly_inputs,
    percentile_rank,
    series,
    yearly_inputs,
)


def test_shift_months_moves_whole_calendar_months():
    assert shift_months("2026-07-01", -12) == "2025-07-01"
    assert shift_months("2026-07-01", 0) == "2026-07-01"
    assert shift_months("2026-01-01", -1) == "2025-12-01"
    assert shift_months("2026-12-01", 2) == "2027-02-01"


def test_shift_months_keeps_the_calendar_month_across_leap_years():
    """The reason this exists at all.

    Twenty years of -365 days drifts by the leap days in between, and a monthly
    index takes the frame at or before the instant, so the comparison lands a
    whole month early without anything looking wrong.
    """
    assert shift_months("2026-07-15", -12 * 20) == "2006-07-15"
    assert shift("2026-07-15", -365 * 20) == "2006-07-20"  # not the same day
    # after four years the day offset has already slipped past the 1st, which
    # for a monthly frame means the month before
    assert shift("2026-03-01", -365 * 4) == "2022-03-02"
    assert shift("2026-01-01", -365 * 4) == "2022-01-02"
    assert shift("2026-03-02", -365 * 4) == "2022-03-03"
    assert shift_months("2024-02-29", -12) == "2023-02-28"
    assert shift_months("2023-02-28", 12) == "2024-02-28"


def test_a_long_run_of_years_never_leaves_the_month():
    for years in range(0, 48):
        for month in range(1, 13):
            moved = shift_months(f"2026-{month:02d}-01", -12 * years)
            assert moved[5:7] == f"{month:02d}"
            assert moved[:4] == str(2026 - years)


def test_shift_months_clamps_a_day_the_target_month_does_not_have():
    assert shift_months("2026-03-31", -1) == "2026-02-28"
    assert shift_months("2024-03-31", -1) == "2024-02-29"


def test_an_input_resolves_its_own_instant():
    assert Input("A").resolve("2026-07-01") == "2026-07-01"
    assert Input("A", offset_days=-365).resolve("2026-07-01") == "2025-07-01"
    assert Input("A", offset_months=-24).resolve("2026-07-01") == "2024-07-01"
    # a baseline year is absolute, and keeps the month that was asked for
    assert Input("A", at_year=1979).resolve("2026-07-01") == "1979-07-01"
    assert Input("A", at_year=1979).resolve("2026-11-20") == "1979-11-01"


def test_an_input_cannot_be_offset_two_ways_at_once():
    with pytest.raises(ValueError, match="days or in months"):
        Input("A", offset_days=-365, offset_months=-12)
    with pytest.raises(ValueError, match="takes no offset"):
        Input("A", at_year=1979, offset_months=-12)


def test_the_generated_inputs_have_the_offsets_they_claim():
    yearly = yearly_inputs("AGERA5-PF-M", years=3)
    assert [i.role for i in yearly] == ["y00", "y01", "y02"]
    assert [i.offset_months for i in yearly] == [0, -12, -24]

    monthly = monthly_inputs("AGERA5-PF-M", months=3, prefix="p")
    assert [i.role for i in monthly] == ["p00", "p01", "p02"]
    assert [i.offset_months for i in monthly] == [0, -1, -2]


def cell(value):
    return np.ma.masked_array(np.array([value], dtype="float64"))


def test_series_stops_where_the_record_does():
    """An offset off the start of the record comes back as the earliest frame.

    The index answers with the frame at or before the instant, and the first
    frame there is when none is, so asking for July 1974 hands back January
    1979: real numbers, of the wrong month, that would sit in a July
    distribution looking exactly like data.
    """
    stack = {"y00": cell(1.0), "y01": cell(2.0), "y02": cell(3.0)}
    params = {
        "time": "1981-07-01",
        "frames": {
            "y00": "1981-07-01",
            "y01": "1980-07-01",
            "y02": "1979-01-01",  # asked for 1979-07, got the start of record
        },
    }
    kept = series(stack, params, "y", 3)
    assert [float(f[0]) for f in kept] == [1.0, 2.0]


def test_series_without_resolved_frames_keeps_everything():
    # Unit tests call compute directly; only the server knows where a read
    # landed, and its absence must not silently empty the stack.
    stack = {"y00": cell(1.0), "y01": cell(2.0)}
    kept = series(stack, {"time": "2026-07-01"}, "y", 2)
    assert len(kept) == 2


def test_percentile_rank_shares_ties():
    """Deserts are mostly ties: many Julys with no rain at all.

    Counting only what is strictly below would call every one of those the
    driest July on record, and a drought declaration argued on that would not
    survive its first challenge.
    """
    data = np.array([[0.0], [0.0], [0.0], [0.0], [50.0]])
    ranked = percentile_rank(data, data[0])
    assert ranked[0] == pytest.approx(40.0)  # four of five tied, half of them

    data = np.array([[10.0], [0.0], [20.0], [30.0], [40.0]])
    assert percentile_rank(data, data[0])[0] == pytest.approx(30.0)
