"""How far the temperature swings in a day."""

from __future__ import annotations

from typing import Any

import numpy as np

from ferspas_tile.analysis import SEQUENTIAL, Analysis, Input


def compute(
    stack: dict[str, np.ma.MaskedArray], params: dict[str, Any]
) -> np.ma.MaskedArray:
    """A wide swing means clear skies and dry air, a narrow one cloud or humidity.

    It is a cheap proxy for conditions a single variable hides.
    """
    return stack["tmax"] - stack["tmin"]


ANALYSIS = Analysis(
    id="diurnal-range",
    title="Diurnal temperature range",
    question="How far did the temperature swing today?",
    unit="K",
    inputs=(Input("AGERA5-TMAX", role="tmax"), Input("AGERA5-TMIN", role="tmin")),
    compute=compute,
    rescale=(0.0, 25.0),
    scale=SEQUENTIAL,
    notes="A wide swing means clear dry air, a narrow one cloud or humidity.",
)
