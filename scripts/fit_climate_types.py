"""Fit the cluster centres in `ferspas_tile.climate_types`, and print them.

k-means on the same four standardised variables the axes use, so that a type
and an axis are two readings of one fit rather than two unrelated maps.

The centres are frozen for the same reason the axes are: clustering per tile
would give each tile its own types, and type 3 in one tile would have nothing
to do with type 3 in the next. Frozen, the assignment is a nearest-centre
lookup per pixel and a tile stays independent of every other tile.

    uv run python scripts/fit_climate_types.py

Choosing k is the part that cannot be automated away. This prints the
silhouette score for a range of k, which is what 005-A in study-geoai-algo-py
uses, and that experiment's own finding is the warning to keep in mind: the
score fell steadily with k and the clusters were never well separated, so the
score picks the least bad k rather than revealing a true number of types.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ferspas_tile.climate_axes import (  # noqa: E402
    MEAN,
    STD,
    VARIABLES,
    WARMTH_AXIS,
    WATER_AXIS,
)
from fit_climate_axes import sample  # noqa: E402

SEED = 0
CANDIDATE_K = range(3, 9)
# Silhouette is quadratic in the number of points, so it is scored on a sample.
SILHOUETTE_POINTS = 20000


def main() -> None:
    rows = sample()
    z = (rows - np.array(MEAN)) / np.array(STD)
    print(f"# fitted on {len(z):,} pixels")

    rng = np.random.default_rng(SEED)
    small = z[rng.choice(len(z), SILHOUETTE_POINTS, replace=False)]

    print("\n# k   silhouette   inertia")
    fits = {}
    for k in CANDIDATE_K:
        model = KMeans(n_clusters=k, n_init=10, random_state=SEED).fit(z)
        score = silhouette_score(small, model.predict(small))
        fits[k] = model
        print(f"# {k}   {score:.4f}   {model.inertia_:,.0f}")

    for k, model in fits.items():
        print(f"\n# --- k = {k} ---")
        counts = np.bincount(model.labels_, minlength=k)
        # Order the types along the warmth axis, coldest first. A hard
        # classification has no inherent order, but the legend has to list them
        # in some order, and k-means numbers its clusters by wherever the seeds
        # happened to land. Warmth was tried against water here and reads
        # better: coldest to hottest is a sequence a reader already has, while
        # driest to wettest put the frozen type in the middle of it.
        order = np.argsort(model.cluster_centers_ @ np.array(WARMTH_AXIS))
        for rank, index in enumerate(order):
            centre = model.cluster_centers_[index]
            real = centre * np.array(STD) + np.array(MEAN)
            share = 100.0 * counts[index] / counts.sum()
            print(
                f"#  {rank}: {share:5.1f}%  "
                + "  ".join(f"{n}={v:7.1f}" for n, v in zip(VARIABLES, real))
                + f"   warmth={centre @ np.array(WARMTH_AXIS):+.2f}"
                + f" water={centre @ np.array(WATER_AXIS):+.2f}"
            )
        print("CENTRES = (")
        for index in order:
            values = ", ".join(f"{v:.6f}" for v in model.cluster_centers_[index])
            print(f"    ({values}),")
        print(")")


if __name__ == "__main__":
    main()
