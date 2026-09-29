"""The rainfall a farmer can count on in four years out of five."""

from __future__ import annotations

from typing import Any

import numpy as np

from ferspas_tile.analysis import SEQUENTIAL, Analysis
from ferspas_tile.climatology import (
    MIN_YEARS,
    RECORD_YEARS,
    cube,
    enough,
    quantile,
    remask,
    series,
    yearly_inputs,
)


# Four years in five: the amount exceeded in eighty percent of years. It is
# not a parameter because the server only forwards the two query parameters it
# knows by name, and a parameter a caller cannot set would be a lie in the
# registry listing.
DEPENDABLE_PERCENTILE = 20.0


def compute(
    stack: dict[str, np.ma.MaskedArray], params: dict[str, Any]
) -> np.ma.MaskedArray:
    """The 20th percentile of this calendar month across the record.

    Not the mean. A mean is a number that a farmer in a variable climate
    receives in about a third of years, and planning against it is how a
    rainfed maize programme ends up recommending a crop that fails one year in
    three. The dependable amount is what an investment appraisal and a farmer
    both actually use.
    """
    frames = series(stack, params, "y", RECORD_YEARS)
    data = cube(frames)
    dependable = quantile(data, DEPENDABLE_PERCENTILE)
    return remask(enough(dependable, data, MIN_YEARS))


ANALYSIS = Analysis(
    id="dependable-rainfall",
    title="Dependable rainfall (four years in five)",
    question="How much rain can this place count on in four years out of five?",
    explanation=(
        "For each place this takes the same calendar month from every year on"
        " record, sorts them from driest to wettest, and reports the amount that"
        " one year in five falls below. That is the rain a farmer can plan"
        " around: in four years out of five there will be at least this much."
        " Bright means plenty even in a poor year, dark means very little can be"
        " relied on. The average is a worse guide, because a few wet years pull"
        " it above what most years actually deliver, and a crop chosen on the"
        " average fails whenever the weather is merely unremarkable."
    ),
    unit="mm/month",
    inputs=yearly_inputs("AGERA5-PF-M"),
    compute=compute,
    rescale=(0.0, 200.0),
    scale=SEQUENTIAL,
    notes=(
        "Forty years of the same calendar month per tile. The top of the range"
        " is 200 mm, so a monsoon month sits at the bright end rather than"
        " stretching the ramp past everywhere else; the interesting contrast is"
        " between 0 and 100 mm, which is where a crop choice is decided."
    ),
)
