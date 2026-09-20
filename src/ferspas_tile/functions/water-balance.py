"""Rain minus what the atmosphere can evaporate."""

from __future__ import annotations

from typing import Any

import numpy as np

from ferspas_tile.analysis import DIVERGING, Analysis, Input


def compute(
    stack: dict[str, np.ma.MaskedArray], params: dict[str, Any]
) -> np.ma.MaskedArray:
    """Positive means water is accumulating.

    Negative means a crop is drawing on soil moisture or irrigation. This is
    the everyday agrometeorological view of whether a place is wet or dry, and
    it needs two variables at once, which is exactly what a single-collection
    tile server cannot do.
    """
    return stack["precipitation"] - stack["reference_et"]


ANALYSIS = Analysis(
    id="water-balance",
    title="Water balance (P - ET0)",
    question="Is this place gaining or losing water today?",
    unit="mm/day",
    inputs=(
        Input("AGERA5-PF", role="precipitation"),
        Input("AGERA5-ET0", role="reference_et"),
    ),
    compute=compute,
    rescale=(-10.0, 10.0),
    scale=DIVERGING,
    neutral=0.0,
    notes=(
        "Zero is the break-even point: rain exactly matches demand. Two"
        " collections read at the same instant on the same grid."
    ),
)
