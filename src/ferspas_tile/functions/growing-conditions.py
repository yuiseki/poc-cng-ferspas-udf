"""Where a crop could grow this month: warm enough and wet enough at once."""

from __future__ import annotations

import calendar
from datetime import date
from typing import Any

import numpy as np

from ferspas_tile.analysis import KELVIN, SEQUENTIAL, Analysis, Input, Parameter

# FAO/IIASA Agro-Ecological Zones counts a day as part of the growing period
# when rainfall covers at least half of what the atmosphere can evaporate.
# Here the same threshold is applied to the month.
AEZ_MOISTURE_FRACTION = 0.5

# A month averaging this many degree-days a day is treated as unrestricted
# warmth. Ten above the base is a comfortably warm month for a base-10 crop.
FULL_WARMTH_PER_DAY = 10.0


def compute(
    stack: dict[str, np.ma.MaskedArray], params: dict[str, Any]
) -> np.ma.MaskedArray:
    """The worse of a warmth score and a moisture score, each in 0..1.

    Taking the minimum rather than an average or a product is Liebig's law of
    the minimum: a field is only as good as whatever is scarcest, and a place
    that is hot and bone dry is no more plantable than one that is wet and
    frozen. An average would rate both as middling and put them beside a place
    that is merely adequate at both, which is the opposite of what is being
    asked.
    """
    base = float(params.get("base_c", 10.0))
    when = date.fromisoformat(params["time"])
    days = calendar.monthrange(when.year, when.month)[1]

    mean_c = ((stack["tmax"] - KELVIN) + (stack["tmin"] - KELVIN)) / 2.0
    degree_days = np.ma.maximum(mean_c - base, 0.0) * days
    warmth = np.ma.minimum(degree_days / (FULL_WARMTH_PER_DAY * days), 1.0)

    # Where the air can barely evaporate anything, water is not what is
    # stopping a crop, so the moisture score is full and warmth decides.
    #
    # Masking here instead was wrong, and the map said so: Siberian winter has
    # a reference evapotranspiration near 0.1 mm for the month, so every pixel
    # came back masked and drew as transparent. Through a light basemap that
    # looks like a high score, when the true answer is a confident zero,
    # because the same month is 35 below freezing.
    demand = stack["reference_et"]
    negligible = demand <= 1.0
    safe = np.ma.where(negligible, 1.0, demand)
    moisture = np.ma.minimum(
        stack["precipitation"] / (AEZ_MOISTURE_FRACTION * safe), 1.0
    )
    moisture = np.ma.where(negligible, 1.0, moisture)

    return np.ma.minimum(warmth, moisture)


ANALYSIS = Analysis(
    id="growing-conditions",
    title="Growing conditions",
    question="Was this month both warm enough and wet enough to grow food?",
    explanation=(
        "Two things have to be true at once for a crop to grow, and this map"
        " scores each of them from nothing to enough and then keeps the worse"
        " one. Warmth comes from the month's temperatures, water from rainfall"
        " measured against how much the air could evaporate. Bright means"
        " neither was in the way. Dark means at least one was, and the map"
        " deliberately does not say which: somewhere hot and bone dry scores"
        " the same as somewhere wet and frozen, because in both places nothing"
        " grows. Averaging the two instead would rate both as middling and put"
        " them beside a place that was merely adequate at both."
    ),
    unit="score",
    inputs=(
        Input("AGERA5-TMAX-AVG-M", role="tmax"),
        Input("AGERA5-TMIN-AVG-M", role="tmin"),
        Input("AGERA5-PF-M", role="precipitation"),
        Input("AGERA5-ET0-M", role="reference_et"),
    ),
    compute=compute,
    rescale=(0.0, 1.0),
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
        "A simplification of FAO/IIASA's Agro-Ecological Zones idea of a"
        " growing period, which counts days where temperature and moisture both"
        " allow growth. The moisture threshold here is the AEZ one, rainfall"
        " over half of reference evapotranspiration. What is missing is soil"
        " moisture storage, so a month living off rain that fell earlier scores"
        " too low, and daily resolution, so a month that is half monsoon and"
        " half drought is averaged into something that happened to neither."
        " GAEZ's own answer is in the catalogue as RES01-LGD, in days per year"
        " rather than per month."
    ),
)
