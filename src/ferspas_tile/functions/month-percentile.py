"""Where this month's rainfall sits in the record for the same month."""

from __future__ import annotations

from typing import Any

import numpy as np

from ferspas_tile.analysis import DIVERGING, Analysis, Input
from ferspas_tile.climatology import (
    MIN_YEARS,
    RECORD_YEARS,
    cube,
    enough,
    percentile_rank,
    remask,
    series,
    yearly_inputs,
)


def compute(
    stack: dict[str, np.ma.MaskedArray], params: dict[str, Any]
) -> np.ma.MaskedArray:
    """Rank this month against the same calendar month of every earlier year.

    Percentage of normal is the usual shortcut and it misleads exactly where
    it matters most: in a dry place 60 percent of the average is an ordinary
    year, because the average is pulled up by a few wet ones. A percentile says
    "the second driest July in forty years", which is a claim a district
    officer can defend.
    """
    frames = series(stack, params, "y", RECORD_YEARS)
    data = cube(frames)
    rank = percentile_rank(data, data[0])
    return remask(enough(rank, data, MIN_YEARS))


ANALYSIS = Analysis(
    id="month-percentile",
    title="Rainfall percentile against the same month in history",
    question="Was this month's rain unusual for the time of year here?",
    explanation=(
        "This map lines up the same calendar month from every year on record"
        " for each place, sorts them, and says where this year's month falls in"
        " that line. Fifty means an ordinary month for the time of year. Ten"
        " means only one year in ten was drier; ninety means only one in ten was"
        " wetter. Blue is wetter than usual and red drier than usual. Comparing"
        " a month with its own history rather than with an average is what makes"
        " a dry place readable: in a desert, sixty percent of the average"
        " rainfall is a perfectly normal year, and a percentile says so while a"
        " percentage does not."
    ),
    unit="percentile",
    inputs=yearly_inputs("AGERA5-PF-M"),
    compute=compute,
    rescale=(0.0, 100.0),
    scale=DIVERGING,
    neutral=50.0,
    notes=(
        "Forty years of the same calendar month are read for every tile, and"
        " the month being asked about is one of them, so the median month of the"
        " record draws as neutral. Ties share a rank, which matters in deserts"
        " where many years record no rain at all in a given month: without that,"
        " every one of those months would come out as the driest ever."
        " A date early enough in the record that fewer than ten years sit behind"
        " it is left blank rather than ranked among a handful of years."
    ),
)
