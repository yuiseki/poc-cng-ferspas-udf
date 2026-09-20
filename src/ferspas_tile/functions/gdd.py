"""Heat available to a crop on one day, above a base temperature."""

from __future__ import annotations

from typing import Any

import numpy as np

from ferspas_tile.analysis import KELVIN, SEQUENTIAL, Analysis, Input, Parameter


def compute(
    stack: dict[str, np.ma.MaskedArray], params: dict[str, Any]
) -> np.ma.MaskedArray:
    """Crops develop on accumulated warmth rather than on calendar days.

    A day colder than the base contributes nothing; it does not subtract
    growth, hence the floor at zero.
    """
    base = float(params.get("base_c", 10.0))
    mean = ((stack["tmax"] - KELVIN) + (stack["tmin"] - KELVIN)) / 2.0
    return np.ma.maximum(mean - base, 0.0)


ANALYSIS = Analysis(
    id="gdd",
    title="Growing degree days",
    question="How much heat did a crop get today?",
    unit="degree-days",
    inputs=(Input("AGERA5-TMAX", role="tmax"), Input("AGERA5-TMIN", role="tmin")),
    compute=compute,
    rescale=(0.0, 20.0),
    scale=SEQUENTIAL,
    parameters=(
        Parameter(
            "base_c",
            "float",
            10.0,
            "Base temperature in Celsius. 10 suits maize, 0 suits wheat.",
        ),
    ),
    notes="AgERA5 temperatures are Kelvin; the conversion happens here.",
)
