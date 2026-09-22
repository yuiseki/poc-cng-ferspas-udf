"""Reading the same tile from many frames, and summarising the stack.

Half of what an agricultural analyst asks for is not "what happened this
month" but "how does this month compare with what normally happens here". That
means reading the same window from the same calendar month of forty years, or
from each of the last twelve months, and reducing the stack per pixel.

Reading that many frames is affordable. The cost of an analysis is the HTTPS
open per COG, not the arithmetic or the bytes, and the reads run in parallel:
thirty frames for one tile measured about 7 s against about 4 s for one.

Two things need care, and both are here rather than repeated in each analysis.

**An offset that runs off the start of the record does not fail.** The index
returns the frame at or before the instant, and the first frame if none is, so
asking AGERA5-PF-M for July 1974 hands back January 1979: a real array, of the
wrong calendar month, that would sit in a July distribution looking like data.
The server records which instant each input actually landed on, and
:func:`series` stops at the first input that did not land where it was sent.
The offsets are monotonic, so everything past that one is off the record too.

**A missing pixel is not the same as an unknown answer.** These reductions use
NaN rather than a mask internally so that a pixel missing from some frames is
still answered from the frames that have it, and only a pixel with nothing
behind it at all comes back masked.
"""

from __future__ import annotations

import warnings
from typing import Any

import numpy as np

from .analysis import Input, shift_months

# How far back the "same calendar month of every year" analyses look. The
# AgERA5 monthly record starts in January 1979, so a request in 2026 has 47
# full years behind it; forty is a round number that still leaves a request in
# the 2010s with a full-length distribution rather than a truncated one.
RECORD_YEARS = 40

# Fewer years than this is not a distribution, it is an anecdote, and a
# percentile out of six values would be a ladder of six colours pretending to
# be a continuum.
MIN_YEARS = 10


def yearly_inputs(
    short_id: str, years: int = RECORD_YEARS, prefix: str = "y"
) -> tuple[Input, ...]:
    """The same calendar month of this year and each of the ``years`` before.

    The offsets are in whole months. In days they would drift: -365 four times
    over lands on the 30th of the month before, and the monthly index takes the
    frame at or before that instant, so the analysis would compare July with
    June without anything looking wrong.
    """
    return tuple(
        Input(short_id, offset_months=-12 * k, role=f"{prefix}{k:02d}")
        for k in range(years)
    )


def monthly_inputs(
    short_id: str, months: int = 12, prefix: str = "m"
) -> tuple[Input, ...]:
    """This month and each of the ``months - 1`` before it."""
    return tuple(
        Input(short_id, offset_months=-k, role=f"{prefix}{k:02d}")
        for k in range(months)
    )


def series(
    stack: dict[str, np.ma.MaskedArray],
    params: dict[str, Any],
    prefix: str,
    count: int,
    step_months: int = 12,
) -> list[np.ma.MaskedArray]:
    """The frames of one input series, in order, stopping where the record does.

    ``params["frames"]`` is what the server resolved each role to. Where an
    offset ran off the start of the record the index returned the earliest
    frame there is, which is a different calendar month; that is dropped rather
    than counted, and so is everything behind it.
    """
    resolved = params.get("frames") or {}
    time = params["time"]
    frames: list[np.ma.MaskedArray] = []
    for k in range(count):
        role = f"{prefix}{k:02d}"
        if role not in stack:
            break
        landed = resolved.get(role)
        if landed is not None and landed[:7] != shift_months(time, -k * step_months)[:7]:
            break
        frames.append(stack[role])
    return frames


def cube(frames: list[np.ma.MaskedArray]) -> np.ndarray:
    """The frames as one array with missing pixels as NaN."""
    return np.stack([np.ma.filled(f.astype("float64"), np.nan) for f in frames])


def remask(values: np.ndarray) -> np.ma.MaskedArray:
    """Back to a masked array: NaN means nothing was behind the pixel."""
    return np.ma.masked_invalid(values)


def enough(values: np.ndarray, data: np.ndarray, minimum: int) -> np.ndarray:
    """NaN out pixels answered from fewer than ``minimum`` frames."""
    counted = np.sum(~np.isnan(data), axis=0)
    return np.where(counted >= minimum, values, np.nan)


def _quietly(fn, *args, **kwargs):
    """A NaN-aware reduction, without the warning for an all-NaN pixel.

    A pixel with nothing behind it in any frame is expected here: it is the
    ocean, or the edge of the grid. NumPy warns and returns NaN, which is
    exactly what is wanted, and the warning would otherwise print once per
    tile and train a reader to ignore warnings.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return fn(*args, **kwargs)


def mean(data: np.ndarray, axis: int = 0) -> np.ndarray:
    return _quietly(np.nanmean, data, axis=axis)


def deviation(data: np.ndarray, axis: int = 0) -> np.ndarray:
    return _quietly(np.nanstd, data, axis=axis)


def quantile(data: np.ndarray, q: float, axis: int = 0) -> np.ndarray:
    return _quietly(np.nanpercentile, data, q, axis=axis)


def percentile_rank(data: np.ndarray, current: np.ndarray) -> np.ndarray:
    """Where ``current`` sits in ``data``, 0 to 100, ties shared.

    The mid-rank form: a value equal to half the record sits at 50 rather than
    at 0 or 100. It matters in dry places, where a run of zero-rainfall months
    is a large block of ties and the naive "fraction strictly below" would call
    every one of them the driest month on record.
    """
    valid = ~np.isnan(data)
    n = valid.sum(axis=0)
    below = np.sum((data < current) & valid, axis=0)
    equal = np.sum((data == current) & valid, axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        rank = 100.0 * (below + 0.5 * equal) / n
    return np.where(n > 0, rank, np.nan)
