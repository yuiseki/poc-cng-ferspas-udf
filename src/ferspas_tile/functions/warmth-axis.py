"""The warm-and-thirsty axis: the first principal component of the four."""

from __future__ import annotations

from typing import Any

import numpy as np

from ferspas_tile.analysis import DIVERGING, Analysis, Input
from ferspas_tile.climate_axes import WARMTH_AXIS, project


def compute(
    stack: dict[str, np.ma.MaskedArray], params: dict[str, Any]
) -> np.ma.MaskedArray:
    return project(stack, WARMTH_AXIS)


ANALYSIS = Analysis(
    id="warmth-axis",
    title="Warm and thirsty, or cold and still",
    question="How far is this month from an average month on Earth?",
    explanation=(
        "Ask what the biggest single difference between one month and another"
        " anywhere on Earth is, and the answer is not rainfall. It is warmth"
        " together with how much water the air can pull out of the ground,"
        " which rise and fall together. This map is that one difference, drawn"
        " directly. Blue is warmer and thirstier than an average month"
        " somewhere on Earth, red is colder and stiller, and the scale is in"
        " standard deviations. It is the plainest of these maps and the least"
        " surprising, which is the point: it accounts for three quarters of all"
        " the variation there is, so whatever is left over for the other maps"
        " to show is what warmth alone does not already explain."
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
        "The first principal component of rainfall, reference"
        " evapotranspiration and the two temperatures, 73.5% of the variance,"
        " fitted once over the whole world and frozen in climate_axes.py. Its"
        " loadings are 0.57 on each temperature, 0.50 on evaporative demand and"
        " 0.31 on rainfall, so calling it warmth is a reading of those numbers"
        " rather than a name given in advance. Read beside water-axis, which is"
        " orthogonal to it: together they are 94.4% of everything these four"
        " variables do."
    ),
)
