"""How long since this place last had rain worth the name."""

from __future__ import annotations

from typing import Any

import numpy as np

from ferspas_tile.analysis import SEQUENTIAL, Analysis
from ferspas_tile.climatology import cube, monthly_inputs, remask, series

MONTHS = 24

# What counts as a month with meaningful rain. Below this, a pastoralist would
# not describe it as having rained.
MEANINGFUL_MM = 20.0


def compute(
    stack: dict[str, np.ma.MaskedArray], params: dict[str, Any]
) -> np.ma.MaskedArray:
    """Walk back from this month until a month with real rain, and count.

    Zero means it rained this month. Twenty-four means it has not rained
    meaningfully in two years, as far back as this looks; the number is
    therefore "at least", not "exactly", at the top of the range.
    """
    rain = cube(series(stack, params, "p", MONTHS, step_months=1))
    wet = np.where(np.isnan(rain), False, rain > MEANINGFUL_MM)

    # The first True down the stack, which is newest first, counting from zero.
    # np.argmax gives the first True, or 0 when there is none, so the
    # "none at all" case is separated out rather than colliding with "this
    # month".
    first = np.argmax(wet, axis=0).astype("float64")
    never = ~np.any(wet, axis=0)
    months = np.where(never, float(len(rain)), first)

    nothing = np.all(np.isnan(rain), axis=0)
    return remask(np.where(nothing, np.nan, months))


ANALYSIS = Analysis(
    id="months-since-rain",
    title="Months since meaningful rain",
    question="How long has it been since this place had usable rain?",
    explanation=(
        "Counting back from the month asked about, this is how many months"
        " passed since the last one that received more than twenty millimetres"
        " of rain, which is about the least that leaves anything behind for"
        " grazing. Dark means it rained this month or last. Bright means it has"
        " been a year or more. It is a crude measure and deliberately so,"
        " because it is close to how pastoralists describe their own conditions,"
        " and it is the number behind advice to sell stock early, behind"
        " emergency water trucking, and behind knowing when herds will cross a"
        " border, which becomes somebody's security problem if nobody saw it"
        " coming."
    ),
    unit="months",
    inputs=monthly_inputs("AGERA5-PF-M", MONTHS, prefix="p"),
    compute=compute,
    rescale=(0.0, 24.0),
    scale=SEQUENTIAL,
    notes=(
        "Twenty-four frames per tile. The scale is bounded by how far back it"
        " looks, so the brightest value means at least two years rather than"
        " exactly two; the true hyper-arid cores of the Sahara and the Atacama"
        " have gone longer than this map can say. Twenty millimetres in a month"
        " is a low bar on purpose: it is the point below which nothing useful"
        " grows, not the point at which a crop is supplied. Near the start of"
        " the record the walk back is cut short by the record itself, and the"
        " count then reads as at least the months that exist."
    ),
)
