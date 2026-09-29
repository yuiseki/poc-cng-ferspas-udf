"""How erosive a year's rain is, from monthly totals alone."""

from __future__ import annotations

from typing import Any

import numpy as np

from ferspas_tile.analysis import SEQUENTIAL, Analysis
from ferspas_tile.climatology import cube, monthly_inputs, remask, series

MONTHS = 12


def compute(
    stack: dict[str, np.ma.MaskedArray], params: dict[str, Any]
) -> np.ma.MaskedArray:
    """The modified Fournier index: sum of monthly totals squared, over the total.

    Squaring each month before adding is the whole idea. Two places with the
    same annual rainfall score differently when one takes it in twelve even
    months and the other in three, and the concentrated one is the one that
    moves soil.

    A year with no rain scores zero rather than nothing: no rain is no erosion,
    which is a determinate answer, and masking it would leave the deserts
    transparent.
    """
    rain = cube(series(stack, params, "p", MONTHS, step_months=1))
    total = np.nansum(rain, axis=0)
    squares = np.nansum(np.square(rain), axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        index = np.where(total > 0.0, squares / np.where(total > 0.0, total, 1.0), 0.0)
    nothing = np.all(np.isnan(rain), axis=0)
    return remask(np.where(nothing, np.nan, index))


ANALYSIS = Analysis(
    id="fournier-erosivity",
    title="Rainfall erosivity (modified Fournier index)",
    question="How hard is the rain here on bare soil?",
    explanation=(
        "Rain does not damage soil in proportion to how much of it falls, but"
        " in proportion to how concentrated it is: a year's rain delivered in"
        " three months strips a bare field in a way the same total spread over"
        " twelve does not. This adds up each of the last twelve months squared"
        " and divides by the year's total, which gives a larger number the more"
        " the rain is concentrated into a few heavy months. Bright means"
        " erosive, dark means gentle or simply dry. It is the case for"
        " terracing, contour bunding and cover crops, and it says when bare soil"
        " is most at risk, which is the gap between preparing the land and the"
        " crop covering it."
    ),
    unit="mm",
    inputs=monthly_inputs("AGERA5-PF-M", MONTHS, prefix="p"),
    compute=compute,
    rescale=(0.0, 200.0),
    scale=SEQUENTIAL,
    notes=(
        "This is not the RUSLE R factor and must not be reported as one: R needs"
        " rainfall intensity at sub-hourly resolution, which monthly totals"
        " cannot recover. The modified Fournier index is the accepted fallback"
        " where only monthly data exists, and regional studies regress R against"
        " it. The conventional classes are very low under 60, low to 90,"
        " moderate to 120, high to 160 and very high above that, so the top of"
        " this ramp is 200. Twelve frames per tile, ending at the date asked"
        " for."
    ),
)
