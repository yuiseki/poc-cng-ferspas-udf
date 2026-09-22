"""The longest run of dry months inside the last twelve."""

from __future__ import annotations

from typing import Any

import numpy as np

from ferspas_tile.analysis import SEQUENTIAL, Analysis
from ferspas_tile.climatology import cube, monthly_inputs, remask, series

MONTHS = 12

# A month is dry when rain covers less than half of what the atmosphere could
# evaporate: the FAO/IIASA Agro-Ecological Zones moisture threshold, the same
# one `growing-conditions` uses.
AEZ_MOISTURE_FRACTION = 0.5


def longest_run(dry: np.ndarray) -> np.ndarray:
    """The longest run of True down the first axis, per pixel."""
    running = np.zeros(dry.shape[1:], dtype="float64")
    best = np.zeros(dry.shape[1:], dtype="float64")
    for month in dry:
        running = np.where(month, running + 1.0, 0.0)
        best = np.maximum(best, running)
    return best


def compute(
    stack: dict[str, np.ma.MaskedArray], params: dict[str, Any]
) -> np.ma.MaskedArray:
    """Flag each of the last twelve months dry or not, then take the longest run.

    The frames arrive newest first, which does not matter: the longest run in a
    sequence is the same read backwards.

    A month where the atmosphere can evaporate almost nothing is not counted as
    dry even if almost no rain fell. That is deliberate and it is the same
    point `growing-conditions` makes about masking: a frozen month has no
    moisture deficit, whatever the rain gauge says, and calling it dry would
    paint Siberia as a twelve-month drought.
    """
    rain = cube(series(stack, params, "p", MONTHS, step_months=1))
    demand = cube(series(stack, params, "e", MONTHS, step_months=1))
    count = min(len(rain), len(demand))
    rain, demand = rain[:count], demand[:count]

    with np.errstate(invalid="ignore"):
        dry = rain < AEZ_MOISTURE_FRACTION * demand
    # A month with nothing behind it cannot break a run and cannot extend one;
    # treating it as wet ends the run, which understates rather than invents.
    dry = np.where(np.isnan(rain) | np.isnan(demand), False, dry)

    runs = longest_run(dry)
    nothing = np.all(np.isnan(rain), axis=0)
    return remask(np.where(nothing, np.nan, runs))


ANALYSIS = Analysis(
    id="consecutive-dry-months",
    title="Longest run of dry months in the last year",
    question="How long does this place go without usable rain?",
    explanation=(
        "A month counts as dry here when the rain that fell covered less than"
        " half of what the sun and wind could have evaporated, which is the"
        " threshold agronomists use for a month in which a crop cannot be"
        " supplied by rain alone. This map looks at the last twelve months and"
        " reports the longest unbroken run of them. Dark is a place that is"
        " rarely without usable rain; bright is a place that went most of the"
        " year without it. The point is not the total: one long dry season is"
        " something farmers plan around by storing grain, while the same number"
        " of dry months split by a failed rainy season is a different emergency."
    ),
    unit="months",
    inputs=(
        monthly_inputs("AGERA5-PF-M", MONTHS, prefix="p")
        + monthly_inputs("AGERA5-ET0-M", MONTHS, prefix="e")
    ),
    compute=compute,
    rescale=(0.0, 12.0),
    scale=SEQUENTIAL,
    notes=(
        "Twenty-four frames per tile, twelve of rainfall and twelve of"
        " evaporative demand. This is a rolling twelve months ending at the"
        " date asked for, not a long-run average, so it answers how the last"
        " year went rather than what is normal. Twelve dry months means every"
        " month of the year fell short, which the deserts do; the interesting"
        " reading is the band between four and eight, where the length of the"
        " dry season decides what can be grown."
    ),
)
