"""The same measurement at two dates, subtracted."""

from __future__ import annotations

from typing import Any

import numpy as np

from ferspas_tile.analysis import DIVERGING, Analysis, Input, Parameter


def compute(
    stack: dict[str, np.ma.MaskedArray], params: dict[str, Any]
) -> np.ma.MaskedArray:
    """The generalised form of what Case5 of the FAO notebooks did.

    That notebook indexed a sorted file list to pick 2001 and 2015, which
    quietly compares different years if a file appears or disappears.
    """
    return stack["value"] - stack["earlier"]


ANALYSIS = Analysis(
    id="change",
    title="Change against the same month last year",
    question="Was this month wetter or drier than the same month a year ago?",
    explanation=(
        "Rainfall for this month with the same month last year taken away, so"
        " the seasons cancel out and what is left is the difference between the"
        " two years. Blue means this year had more rain, red means less. It says"
        " nothing about whether that is welcome: less rain is a problem during a"
        " drought and a relief during a flood, and a map cannot tell which one"
        " you are looking at."
    ),
    unit="mm/month",
    inputs=(
        Input("AGERA5-PF-M", role="value"),
        Input("AGERA5-PF-M", offset_days=-365, role="earlier"),
    ),
    compute=compute,
    rescale=(-200.0, 200.0),
    scale=DIVERGING,
    neutral=0.0,
    parameters=(
        Parameter(
            "offset_days",
            "int",
            -365,
            "How far back the comparison month is, in days. -365 is a year.",
        ),
    ),
    notes=(
        "The offset is resolved against the months that exist, so it steps to"
        " the nearest earlier frame rather than failing."
    ),
)
