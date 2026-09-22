"""The UNEP aridity index: a year of rain against a year of demand."""

from __future__ import annotations

from typing import Any

import numpy as np

from ferspas_tile.analysis import SEQUENTIAL, Analysis
from ferspas_tile.climatology import cube, monthly_inputs, remask, series

MONTHS = 12

# The UNEP dryland classes, for the notes and for anyone reading the ramp.
CLASSES = (
    ("hyper-arid", 0.05),
    ("arid", 0.20),
    ("semi-arid", 0.50),
    ("dry sub-humid", 0.65),
)

# A year in which the atmosphere could evaporate less than this is a place
# where the ratio has no useful meaning.
NEGLIGIBLE_MM = 1.0


def compute(
    stack: dict[str, np.ma.MaskedArray], params: dict[str, Any]
) -> np.ma.MaskedArray:
    """Twelve months of rainfall summed, over twelve months of demand summed.

    Summing first and dividing once is not the same as averaging twelve monthly
    ratios, and the annual form is the one the index is defined in: a
    Mediterranean winter with rain far above demand would otherwise cancel out
    a summer with none, and the place would come out looking humid.
    """
    rain = cube(series(stack, params, "p", MONTHS, step_months=1))
    demand = cube(series(stack, params, "e", MONTHS, step_months=1))
    count = min(len(rain), len(demand))
    rain, demand = rain[:count], demand[:count]

    total_rain = np.nansum(rain, axis=0)
    total_demand = np.nansum(demand, axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        index = total_rain / total_demand
    # Where the air cannot evaporate a millimetre in a whole year, rain is not
    # the limit on anything and the ratio would be a division by nothing. That
    # is the wet end of this scale, not an unknown; masking it would leave the
    # ice caps transparent, which reads as arid over a light basemap. Measured,
    # this guard never fires: the lowest annual demand found anywhere in a
    # southern tile including Antarctica was 55 mm. It is here so that a place
    # that does reach zero is answered rather than dropped.
    index = np.where(total_demand < NEGLIGIBLE_MM, 1.0, index)
    nothing = np.all(np.isnan(rain), axis=0) | np.all(np.isnan(demand), axis=0)
    return remask(np.where(nothing, np.nan, index))


ANALYSIS = Analysis(
    id="aridity-annual",
    title="Aridity index over a year",
    question="Can rain meet the atmosphere's demand for water over a whole year?",
    explanation=(
        "Add up a year of rainfall, add up a year of what the sun and wind could"
        " evaporate over the same ground, and divide the first by the second."
        " One means a year's rain exactly matched a year's demand. A fifth means"
        " four fifths of the demand went unmet, which is a desert. Dark is dry"
        " and bright is humid. This is the number drylands are officially"
        " defined by, so the boundaries have consequences: under 0.05 is"
        " hyper-arid, under 0.20 arid, under 0.50 semi-arid, under 0.65 dry"
        " sub-humid, and above that humid. Eligibility for dryland climate"
        " finance, and whether rainfed cereals are defensible at all, are argued"
        " on which side of those lines a district falls."
    ),
    unit="ratio",
    inputs=(
        monthly_inputs("AGERA5-PF-M", MONTHS, prefix="p")
        + monthly_inputs("AGERA5-ET0-M", MONTHS, prefix="e")
    ),
    compute=compute,
    rescale=(0.0, 1.0),
    scale=SEQUENTIAL,
    notes=(
        "This overlaps the existing `aridity`, and the difference is the"
        " interval, which changes what the number means. `aridity` is one"
        " month's rain over the same month's demand, on a diverging ramp about"
        " one, and it answers whether a crop could have been kept supplied by"
        " rain during that particular month; it moves with the seasons and a"
        " single place swings across the whole ramp through the year. This one"
        " sums twelve months before dividing, which is how UNEP defines the"
        " index that drylands are classified by, so it barely moves from month"
        " to month and describes the climate of a place rather than its"
        " weather. A Mediterranean winter reads as wet on the monthly map and"
        " the place still reads as semi-arid on this one, which is correct on"
        " both counts. Values above one are clipped, so the wet tropics are a"
        " single bright class rather than a stretched ramp nobody reads."
    ),
)
