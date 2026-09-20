"""How much hotter the afternoon is than the night."""

from __future__ import annotations

from typing import Any

import numpy as np

from ferspas_tile.analysis import SEQUENTIAL, Analysis, Input


def compute(
    stack: dict[str, np.ma.MaskedArray], params: dict[str, Any]
) -> np.ma.MaskedArray:
    """Both inputs are monthly averages, so this is the average day's swing."""
    return stack["tmax"] - stack["tmin"]


ANALYSIS = Analysis(
    id="diurnal-range",
    title="Day-night temperature gap",
    question="How far did the temperature swing between afternoon and night?",
    explanation=(
        "The difference between a typical afternoon and the night that follows"
        " it. A large gap means clear skies and dry air: nothing holds the day's"
        " heat in, so it escapes after dark. A small gap means cloud or humidity"
        " trapped it. One number therefore says something about the character of"
        " the weather, not just its temperature, and it separates a dry heat"
        " from a muggy one without needing a humidity measurement."
    ),
    unit="K",
    inputs=(
        Input("AGERA5-TMAX-AVG-M", role="tmax"),
        Input("AGERA5-TMIN-AVG-M", role="tmin"),
    ),
    compute=compute,
    rescale=(0.0, 20.0),
    scale=SEQUENTIAL,
    notes="Monthly averages damp the extremes, so the top of the range is 20 K.",
)
