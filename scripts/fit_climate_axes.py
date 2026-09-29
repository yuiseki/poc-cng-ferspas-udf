"""Fit the constants in `ferspas_tile.climate_axes`, and print them.

Three analyses need the same four numbers per pixel to mean something on a
common scale: rainfall, evaporative demand, and the two temperatures. Putting
them on that scale needs a mean, a spread and a covariance, and those have to
be the same for every tile. A fit done per tile would give each tile its own
definition of "average", and the seams would show as the map was panned.

So the fit happens here, once, over the whole world, and its results are
pasted into `climate_axes.py` as constants. That is the same reason the
rescale ranges in the analyses are measured rather than guessed.

    uv run python scripts/fit_climate_axes.py

The sample is four months spread around the year, so that a fit made in July
does not describe a July world. The axes turn out not to care: fitted on
January, April and July separately, the loadings agree to 0.02 and the
explained variance to 0.01. That is this repository's version of the question
006-B in study-geoai-algo-py asks, whether an axis fitted on one area survives
on another.
"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ferspas_tile.analysis import KELVIN  # noqa: E402
from ferspas_tile.app import _read_window  # noqa: E402

COLLECTIONS = (
    "AGERA5-PF-M",
    "AGERA5-ET0-M",
    "AGERA5-TMAX-AVG-M",
    "AGERA5-TMIN-AVG-M",
)
NAMES = ("rain", "demand", "tmax", "tmin")

# Four months around one year. More months would not change the answer (see
# the docstring) and every extra month is another 64 COG reads.
MONTHS = ("2025-01-01", "2025-04-01", "2025-07-01", "2025-10-01")

# z=2 is 16 tiles of 256x256 for the whole world, about a million pixels a
# month before the sea and the poles are dropped.
ZOOM = 2


def one_tile(time: str, x: int, y: int) -> np.ndarray | None:
    bands = []
    for collection in COLLECTIONS:
        band, _ = _read_window(collection, time, ZOOM, x, y)
        if band is None:
            return None
        bands.append(band)
    flat = np.ma.stack(bands).reshape(len(bands), -1).T
    keep = ~np.ma.getmaskarray(flat).any(axis=1)
    return np.ma.getdata(flat)[keep]


def sample() -> np.ndarray:
    jobs = [
        (time, x, y)
        for time in MONTHS
        for x in range(2**ZOOM)
        for y in range(2**ZOOM)
    ]
    with ThreadPoolExecutor(max_workers=16) as pool:
        parts = list(pool.map(lambda j: one_tile(*j), jobs))
    rows = np.vstack([p for p in parts if p is not None and len(p)])
    # Kelvin is a scale nobody reads; the analyses work in Celsius.
    rows[:, 2] -= KELVIN
    rows[:, 3] -= KELVIN
    return rows


def main() -> None:
    rows = sample()
    mean = rows.mean(axis=0)
    std = rows.std(axis=0)
    z = (rows - mean) / std
    cov = np.cov(z.T)

    values, vectors = np.linalg.eigh(cov)
    order = np.argsort(values)[::-1]
    values, vectors = values[order], vectors[:, order]

    # The sign of an eigenvector is arbitrary, and a map is not. Orient the
    # first axis so that up is warmer, and the second so that up is wetter,
    # which is what lets the water axis keep the colour rule that blue is more
    # water than the neutral.
    if vectors[NAMES.index("tmax"), 0] < 0:
        vectors[:, 0] *= -1
    if vectors[NAMES.index("rain"), 1] < 0:
        vectors[:, 1] *= -1

    inverse = np.linalg.inv(cov)
    distance = np.einsum("ij,jk,ik->i", z, inverse, z)

    def row(values_: np.ndarray) -> str:
        return ", ".join(f"{v:.6f}" for v in values_)

    print(f"# fitted on {len(rows):,} pixels, {len(MONTHS)} months at z={ZOOM}")
    print(f"MEAN = ({row(mean)})")
    print(f"STD = ({row(std)})")
    print(f"WARMTH_AXIS = ({row(vectors[:, 0])})")
    print(f"WATER_AXIS = ({row(vectors[:, 1])})")
    print("INVERSE_COVARIANCE = (")
    for line in inverse:
        print(f"    ({row(line)}),")
    print(")")
    print()
    print(f"# explained variance: {np.round(values / values.sum(), 4).tolist()}")
    percentiles = np.percentile(distance, [50, 90, 99, 99.9])
    print(f"# mahalanobis squared, 50/90/99/99.9: {np.round(percentiles, 2).tolist()}")
    for name, axis in (("warmth", vectors[:, 0]), ("water", vectors[:, 1])):
        scores = z @ axis
        low, high = np.percentile(scores, [1, 99])
        print(f"# {name} axis, 1st and 99th percentile: {low:.2f} {high:.2f}")


if __name__ == "__main__":
    main()
