"""How rare this month's combination of four measurements is, anywhere."""

from __future__ import annotations

from typing import Any

import numpy as np

from ferspas_tile.analysis import SEQUENTIAL, Analysis, Input
from ferspas_tile.climate_axes import mahalanobis_squared


def compute(
    stack: dict[str, np.ma.MaskedArray], params: dict[str, Any]
) -> np.ma.MaskedArray:
    return mahalanobis_squared(stack)


ANALYSIS = Analysis(
    id="unusual-combination",
    title="An unusual combination",
    question="Is this combination of rain, heat and demand one that hardly occurs?",
    explanation=(
        "Every other map here asks whether one quantity is high or low. This"
        " one asks whether four of them together make a combination that"
        " hardly happens anywhere. A hot month is ordinary and a wet month is"
        " ordinary, and a place that is both, or one where the days are hot"
        " while the nights stay cold, can still be somewhere the world has very"
        " few of. Bright means unusual. The reason it is not simply the four"
        " differences added up is that the four are not independent: warmth and"
        " evaporative demand rise together almost everywhere, so counting both"
        " would count the same fact twice, and pulling apart two measurements"
        " that normally move together is far stranger than moving both a long"
        " way in the same direction."
    ),
    unit="distance squared",
    inputs=(
        Input("AGERA5-PF-M", role="rain"),
        Input("AGERA5-ET0-M", role="demand"),
        Input("AGERA5-TMAX-AVG-M", role="tmax"),
        Input("AGERA5-TMIN-AVG-M", role="tmin"),
    ),
    compute=compute,
    rescale=(0.0, 30.0),
    scale=SEQUENTIAL,
    notes=(
        "The squared Mahalanobis distance from the world's average month,"
        " using the covariance frozen in climate_axes.py. The range is"
        " measured, not assumed: over 1.86 million pixels in four months the"
        " median is 2.3, the 99th percentile 29.7, so 30 is where the bright"
        " end belongs. The textbook reading of this number, as a chi-square"
        " with four degrees of freedom, does not hold here and the same"
        " measurement is what says so: a chi-square with four degrees of"
        " freedom has a median of 3.4 and this has 2.3, because the four"
        " variables are not jointly normal. So the number ranks places against"
        " each other and does not give a probability. It also compares against"
        " the world rather than against this place's own history, which is a"
        " different question and the one month-percentile asks."
    ),
)
