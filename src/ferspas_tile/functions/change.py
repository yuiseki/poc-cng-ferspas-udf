"""This instant minus an earlier one of the same variable."""

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
    title="Change against an earlier date",
    question="How does today compare with a year ago?",
    unit="same as input",
    inputs=(
        Input("AGERA5-PF", role="value"),
        Input("AGERA5-PF", offset_days=-365, role="earlier"),
    ),
    compute=compute,
    rescale=(-10.0, 10.0),
    scale=DIVERGING,
    neutral=0.0,
    parameters=(
        Parameter(
            "offset_days",
            "int",
            -365,
            "How far back the comparison frame is, in days.",
        ),
    ),
    notes=(
        "Red is drier than the earlier date and blue wetter, which is a"
        " direction and not a verdict. The offset is resolved against the"
        " timestamps that exist, so a missing day steps to the nearest earlier"
        " frame rather than failing."
    ),
)
