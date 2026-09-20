"""Warmth a crop could use during the month."""

from __future__ import annotations

import calendar
from datetime import date
from typing import Any

import numpy as np

from ferspas_tile.analysis import KELVIN, SEQUENTIAL, Analysis, Input, Parameter


def days_in_month(time: str) -> int:
    """Length of the month a YYYY-MM-DD string falls in."""
    when = date.fromisoformat(time)
    return calendar.monthrange(when.year, when.month)[1]


def compute(
    stack: dict[str, np.ma.MaskedArray], params: dict[str, Any]
) -> np.ma.MaskedArray:
    """Average daily warmth above the base, accumulated over the month.

    The inputs are the month's average daily maximum and minimum, so their
    midpoint is an average day. A month colder than the base contributes
    nothing; it does not subtract growth, hence the floor at zero.
    """
    base = float(params.get("base_c", 10.0))
    mean = ((stack["tmax"] - KELVIN) + (stack["tmin"] - KELVIN)) / 2.0
    per_day = np.ma.maximum(mean - base, 0.0)
    return per_day * days_in_month(params["time"])


ANALYSIS = Analysis(
    id="gdd",
    title="Growing degree days",
    question="How much usable warmth did a crop get this month?",
    explanation=(
        "Crops develop on warmth rather than on dates: a cool month moves a"
        " maize plant along less than a warm one, so calendars are a poor guide"
        " to when a field will be ready. This counts how far the average day sat"
        " above the temperature a crop needs to grow at all, added up across the"
        " month. Bright means a crop could develop quickly there. Dark means it"
        " was too cold to grow, which is why the high latitudes and the"
        " mountains go black."
    ),
    unit="degree-days",
    inputs=(
        Input("AGERA5-TMAX-AVG-M", role="tmax"),
        Input("AGERA5-TMIN-AVG-M", role="tmin"),
    ),
    compute=compute,
    rescale=(0.0, 600.0),
    scale=SEQUENTIAL,
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
        "AgERA5 temperatures are Kelvin; the conversion happens here. A hot"
        " tropical month reaches about 600."
    ),
)
