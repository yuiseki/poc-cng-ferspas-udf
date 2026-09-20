"""Rain minus what the sun and wind take back."""

from __future__ import annotations

from typing import Any

import numpy as np

from ferspas_tile.analysis import DIVERGING, Analysis, Input


def compute(
    stack: dict[str, np.ma.MaskedArray], params: dict[str, Any]
) -> np.ma.MaskedArray:
    """Both inputs are millimetres over the same month, so this subtracts."""
    return stack["precipitation"] - stack["reference_et"]


ANALYSIS = Analysis(
    id="water-balance",
    title="Water balance (rain minus evaporation)",
    question="Did this place gain or lose water this month?",
    explanation=(
        "Rain puts water into the ground. Sun and wind take it back out again."
        " This map subtracts the second from the first. Blue means more water"
        " arrived than left, so the ground is wetting up. Red means the"
        " opposite, and anything growing there is living on water stored in the"
        " soil earlier, or on irrigation. It takes two separate measurements to"
        " say this, which is why no single layer in the catalogue shows it."
    ),
    unit="mm/month",
    inputs=(
        Input("AGERA5-PF-M", role="precipitation"),
        Input("AGERA5-ET0-M", role="reference_et"),
    ),
    compute=compute,
    rescale=(-200.0, 200.0),
    scale=DIVERGING,
    neutral=0.0,
    notes=(
        "Zero is the break-even point: rain exactly matches what the air can"
        " evaporate. Clipped at 200 mm either way; a monsoon month reaches 400."
    ),
)
