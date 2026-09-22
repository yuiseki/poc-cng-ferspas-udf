"""Warmth this month against the same month twenty years ago."""

from __future__ import annotations

import calendar
from datetime import date
from typing import Any

import numpy as np

from ferspas_tile.analysis import KELVIN, DIVERGING, Analysis, Input, Parameter

YEARS_BACK = 20

# Maize stops accumulating useful development above this, so the conventional
# correction caps the daily maximum before averaging. It matters in hot
# lowlands, where without the cap a place that is already too hot to grow maize
# keeps accruing degree-days and looks as though it is improving.
CAP_C = 30.0


def degree_days(
    tmax: np.ma.MaskedArray, tmin: np.ma.MaskedArray, base: float, days: int
) -> np.ma.MaskedArray:
    capped = np.ma.minimum(tmax - KELVIN, CAP_C)
    mean = (capped + (tmin - KELVIN)) / 2.0
    return np.ma.maximum(mean - base, 0.0) * days


def compute(
    stack: dict[str, np.ma.MaskedArray], params: dict[str, Any]
) -> np.ma.MaskedArray:
    """Degree-days now, minus degree-days for the same month two decades back.

    The same calendar month both times, because the question is about the
    climate rather than the season. The offset is in months for that reason: at
    -365 days a year, twenty years of leap days add up to five days, and the
    monthly index takes the frame at or before the instant, so the comparison
    would land in the month before and the map would mostly show the shape of
    the seasonal cycle.
    """
    base = float(params.get("base_c", 10.0))
    when = date.fromisoformat(params["time"])
    days = calendar.monthrange(when.year, when.month)[1]
    then = when.year - YEARS_BACK
    days_then = calendar.monthrange(then, when.month)[1]

    now = degree_days(stack["tmax"], stack["tmin"], base, days)
    before = degree_days(stack["tmax_then"], stack["tmin_then"], base, days_then)
    return now - before


ANALYSIS = Analysis(
    id="gdd-shift",
    title="Change in growing degree days over twenty years",
    question="Is there more usable warmth here than there was twenty years ago?",
    explanation=(
        "Crops develop on accumulated warmth rather than on the calendar, and"
        " how much warmth a place delivers decides which varieties can be"
        " planted there. This counts the warmth available this month and"
        " subtracts the warmth the same month delivered twenty years ago. Blue"
        " means more warmth now, red means less, and white means no change. It"
        " is a variety recommendation tool: where the number has risen, a"
        " longer-duration and higher-yielding variety may now finish, which in"
        " highland East Africa and the Andes means cropping is moving uphill."
        " That is an opportunity and also a warning, because the land it moves"
        " onto is usually forest."
    ),
    unit="degree-days",
    inputs=(
        Input("AGERA5-TMAX-AVG-M", role="tmax"),
        Input("AGERA5-TMIN-AVG-M", role="tmin"),
        Input("AGERA5-TMAX-AVG-M", offset_months=-12 * YEARS_BACK, role="tmax_then"),
        Input("AGERA5-TMIN-AVG-M", offset_months=-12 * YEARS_BACK, role="tmin_then"),
    ),
    compute=compute,
    rescale=(-100.0, 100.0),
    scale=DIVERGING,
    neutral=0.0,
    parameters=(
        Parameter(
            "base_c",
            "float",
            10.0,
            "Temperature a crop starts growing at, in Celsius."
            " 10 suits maize, 0 suits wheat.",
        ),
    ),
    notes=(
        "Unlike the plain `gdd` analysis, the daily maximum is capped at 30 C"
        " before averaging. Above that maize gains no further development, and"
        " without the cap the hot lowlands would show the largest gains of"
        " anywhere, which reads as an improvement where the truth is the"
        " opposite. Two dates twenty years apart are two weather months, not two"
        " climates, so a single tile carries the year's noise as well as the"
        " trend; the signal is in what is consistent across several months, not"
        " in one. Dates before 1999 cannot reach twenty years back and fall"
        " against the start of the record instead."
    ),
)
