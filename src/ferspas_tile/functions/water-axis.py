"""The wet-or-dry axis: the second principal component of the four variables."""

from __future__ import annotations

from typing import Any

import numpy as np

from ferspas_tile.analysis import DIVERGING, Analysis, Input
from ferspas_tile.climate_axes import WATER_AXIS, project


def compute(
    stack: dict[str, np.ma.MaskedArray], params: dict[str, Any]
) -> np.ma.MaskedArray:
    return project(stack, WATER_AXIS)


ANALYSIS = Analysis(
    id="water-axis",
    title="Wet or dry for a place like this",
    question="Is this month wet or dry once its temperature is accounted for?",
    explanation=(
        "Rainfall on its own does not say whether a place is wet, because a"
        " cool place needs far less rain than a hot one to be well watered."
        " This map takes all four monthly measurements at once, rainfall, how"
        " much the air could evaporate, and the day and night temperatures, and"
        " reads off one number: where the month sits between dry and wet"
        " compared with an average month somewhere on Earth. Blue is wetter"
        " than that average, red is drier, and the scale is in standard"
        " deviations, so three is about as far as the world goes. The axis"
        " itself was not chosen by hand. It is the second direction that the"
        " world's own variation runs in, after warmth, and it turned out to be"
        " almost entirely about water."
    ),
    unit="standard deviations",
    inputs=(
        Input("AGERA5-PF-M", role="rain"),
        Input("AGERA5-ET0-M", role="demand"),
        Input("AGERA5-TMAX-AVG-M", role="tmax"),
        Input("AGERA5-TMIN-AVG-M", role="tmin"),
    ),
    compute=compute,
    rescale=(-3.0, 3.0),
    scale=DIVERGING,
    neutral=0.0,
    notes=(
        "The second principal component of rainfall, reference"
        " evapotranspiration and the two temperatures, fitted once over the"
        " whole world by scripts/fit_climate_axes.py and frozen in"
        " climate_axes.py. It carries 20.9% of the variance, its loading on"
        " rainfall is 0.91 and its loadings on the two temperatures are under"
        " 0.1, which is why it can be called a water axis rather than named"
        " after a component number. Fitting per tile instead would give every"
        " tile its own average month and put seams in the map. What it is not"
        " is a drought index: it compares this month against the world, not"
        " against this place's own normal, and a dry month in a desert is"
        " ordinary there. RES01-LGD in the catalogue and the month-percentile"
        " draft both answer that other question."
    ),
)
