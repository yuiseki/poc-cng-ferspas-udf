"""How unreliable the rain is, as a share of its own average."""

from __future__ import annotations

from typing import Any

import numpy as np

from ferspas_tile.analysis import SEQUENTIAL, Analysis
from ferspas_tile.climatology import (
    MIN_YEARS,
    RECORD_YEARS,
    cube,
    deviation,
    enough,
    mean as nan_mean,
    remask,
    series,
    yearly_inputs,
)

# Above this much year-to-year variation, rainfed cropping is conventionally
# treated as marginal.
MARGINAL_CV = 30.0

# The top of the displayed range, and the value a place with no rain worth
# measuring is given. See the comment in compute.
FULLY_UNRELIABLE = 150.0

# Below this monthly average, dividing by the mean stops meaning anything.
NEGLIGIBLE_MM = 0.5


def compute(
    stack: dict[str, np.ma.MaskedArray], params: dict[str, Any]
) -> np.ma.MaskedArray:
    """Standard deviation over mean, as a percentage, across the record.

    Where the average month has essentially no rain, the ratio is a division by
    nothing. Masking it would be wrong in the way `growing-conditions`
    documents: the whole Sahara would turn transparent, and transparent over a
    light basemap reads as a low value, when the answer is not unknown at all.
    A place that averages a tenth of a millimetre has rainfall that cannot be
    relied on for anything, which is the top of this scale, so that is what it
    is given.
    """
    frames = series(stack, params, "y", RECORD_YEARS)
    data = cube(frames)
    average = nan_mean(data)
    spread = deviation(data)
    with np.errstate(invalid="ignore", divide="ignore"):
        cv = 100.0 * spread / average
    cv = np.where(average < NEGLIGIBLE_MM, FULLY_UNRELIABLE, cv)
    return remask(enough(cv, data, MIN_YEARS))


ANALYSIS = Analysis(
    id="rainfall-variability",
    title="Rainfall variability",
    question="How unreliable is this month's rain from year to year?",
    explanation=(
        "Two places can receive the same rain on average and be completely"
        " different to farm. This map measures how far each year's rainfall"
        " strays from that place's own average for the month, and reports the"
        " spread as a percentage of the average, so a wet place and a dry one"
        " can be compared. Dark means the rain arrives in much the same amount"
        " every year. Bright means it does not, and a crop chosen on the average"
        " will fail regularly. Above about thirty percent, rainfed cropping is"
        " conventionally treated as marginal. Nothing here says whether the"
        " rainfall is enough, only whether it can be counted on."
    ),
    unit="%",
    inputs=yearly_inputs("AGERA5-PF-M"),
    compute=compute,
    rescale=(0.0, FULLY_UNRELIABLE),
    scale=SEQUENTIAL,
    notes=(
        "Rising variability with an unchanged average is a real and commonly"
        " reported pattern, and it changes the risk a farmer carries without"
        " moving any long-term average. Thirty percent, the conventional line"
        " for marginal rainfed cropping, sits a fifth of the way up the ramp."
        " Places averaging under half a millimetre for the month are drawn at"
        " the top of the scale rather than left blank: their rain is not"
        " unknown, it is absent, and absent rain is the least dependable of all."
    ),
)
