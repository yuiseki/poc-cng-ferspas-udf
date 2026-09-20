"""The same two numbers as a ratio instead of a difference."""

from __future__ import annotations

from typing import Any

import numpy as np

from ferspas_tile.analysis import DIVERGING, Analysis, Input


def compute(
    stack: dict[str, np.ma.MaskedArray], params: dict[str, Any]
) -> np.ma.MaskedArray:
    """Demand at or near zero is masked rather than divided by."""
    demand = np.ma.masked_less_equal(stack["reference_et"], 1.0)
    return np.ma.minimum(stack["precipitation"] / demand, 2.0)


ANALYSIS = Analysis(
    id="aridity",
    title="Aridity (rain as a share of demand)",
    question="Could rain alone keep a crop supplied this month?",
    explanation=(
        "The same two measurements as the water balance, divided instead of"
        " subtracted. One means the rain exactly covered what the air could"
        " evaporate. Below one, rain alone was not enough and the shortfall has"
        " to come from somewhere else. Dividing rather than subtracting makes"
        " places comparable: a cool damp month in Ireland and a hot wet month in"
        " Kenya have very different millimetres but can sit at the same ratio."
    ),
    unit="ratio",
    inputs=(
        Input("AGERA5-PF-M", role="precipitation"),
        Input("AGERA5-ET0-M", role="reference_et"),
    ),
    compute=compute,
    rescale=(0.0, 2.0),
    scale=DIVERGING,
    neutral=1.0,
    notes=(
        "One is the break-even point, so the range is symmetric around it."
        " Capped at 2 so a very wet month does not flatten the rest of the ramp."
        " This is the interval the index is normally read over; the same"
        " calculation on a single day only says whether it happened to rain."
    ),
)
