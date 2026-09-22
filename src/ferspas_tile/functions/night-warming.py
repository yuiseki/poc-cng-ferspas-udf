"""This month's nights against the nights of 1979 to 1998."""

from __future__ import annotations

from typing import Any

import numpy as np

from ferspas_tile.analysis import DIVERGING, Analysis, Input
from ferspas_tile.climatology import cube, mean, remask

# The baseline period, in calendar years. It is stated as years rather than as
# a distance from the request because that is what a baseline is: "warmer than
# 1979 to 1998" means the same thing whichever month is being asked about, and
# an offset would slide the baseline along with the date.
BASELINE_FIRST = 1979
BASELINE_LAST = 1998


def compute(
    stack: dict[str, np.ma.MaskedArray], params: dict[str, Any]
) -> np.ma.MaskedArray:
    """This month's mean minimum temperature, minus the baseline mean.

    Both are Kelvin, and the answer is a difference, so no conversion is
    needed: a kelvin and a degree Celsius are the same size.
    """
    baseline = cube(
        [
            stack[f"b{year}"]
            for year in range(BASELINE_FIRST, BASELINE_LAST + 1)
            if f"b{year}" in stack
        ]
    )
    normal = mean(baseline)
    return stack["tmin"] - remask(normal)


ANALYSIS = Analysis(
    id="night-warming",
    title="Night warming against 1979 to 1998",
    question="Are the nights here warmer than they were a generation ago?",
    explanation=(
        "Every night a crop burns some of what it made during the day, and it"
        " burns more when the night is warm. This map takes the average of the"
        " lowest daily temperatures in this month and subtracts the average of"
        " the same calendar month over the twenty years from 1979 to 1998. Blue"
        " means the nights are warmer than they were, red means cooler, white"
        " means unchanged. Roughly a tenth of a rice crop is lost for each"
        " degree the nights warm, and the loss is invisible to anyone watching"
        " only daytime maxima, which is why a conversation about a bad harvest"
        " is so often about drought when the cause was the dark hours."
    ),
    unit="K",
    inputs=(
        (Input("AGERA5-TMIN-AVG-M", role="tmin"),)
        + tuple(
            Input("AGERA5-TMIN-AVG-M", at_year=year, role=f"b{year}")
            for year in range(BASELINE_FIRST, BASELINE_LAST + 1)
        )
    ),
    compute=compute,
    rescale=(-3.0, 3.0),
    scale=DIVERGING,
    neutral=0.0,
    notes=(
        "Twenty-one frames per tile: this month, and the same calendar month of"
        " each of the twenty baseline years. The baseline is fixed in calendar"
        " years rather than expressed as an offset, because a baseline that"
        " slides with the date being viewed is not a baseline; the framework"
        " gained an absolute `at_year` input for this. One month against a"
        " twenty-year mean still contains that month's weather, so a single"
        " tile is not evidence of a trend on its own. The range is three kelvin"
        " either way, which measured against July 2026 clips about a tenth of"
        " the land: the high latitudes swing much further than the tropics in a"
        " single month, and widening the range to fit them would flatten the"
        " place where a tenth of a rice crop is decided."
    ),
)
