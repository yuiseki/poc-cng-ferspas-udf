"""Rain as a fraction of atmospheric demand."""

from __future__ import annotations

from typing import Any

import numpy as np

from ferspas_tile.analysis import DIVERGING, Analysis, Input


def compute(
    stack: dict[str, np.ma.MaskedArray], params: dict[str, Any]
) -> np.ma.MaskedArray:
    """Below about 0.5 a place cannot meet crop water demand from rain alone.

    Unlike the plain difference this is comparable between a cool wet place and
    a hot wet one. Demand at or near zero is masked rather than divided by.
    """
    demand = np.ma.masked_less_equal(stack["reference_et"], 0.01)
    return np.ma.minimum(stack["precipitation"] / demand, 2.0)


ANALYSIS = Analysis(
    id="aridity",
    title="Aridity ratio (P / ET0)",
    question="Can rain alone meet the atmospheric demand here?",
    unit="ratio",
    inputs=(
        Input("AGERA5-PF", role="precipitation"),
        Input("AGERA5-ET0", role="reference_et"),
    ),
    compute=compute,
    rescale=(0.0, 2.0),
    scale=DIVERGING,
    neutral=1.0,
    notes=(
        "One is the break-even point: rain exactly equals demand, so the range"
        " is symmetric around it. Capped at 2 so a wet day does not flatten the"
        " rest of the ramp. Read over a single day this answers whether it"
        " rained enough today, not whether the climate is dry; for that, point"
        " it at the monthly collections."
    ),
)
