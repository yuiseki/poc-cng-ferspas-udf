"""Four kinds of month, found by k-means and then frozen.

Fitted by `scripts/fit_climate_types.py` on the same 1.86 million pixels and
the same standardised four variables as `climate_axes`, so that a type and an
axis are two readings of one fit.

Frozen for the same reason the axes are, and more urgently. Clustering per tile
would not merely shift the scale, it would renumber the types: type 2 in one
tile would have nothing to do with type 2 in the next, and the map would be
meaningless rather than merely seamed.

What k-means does not give is k. The silhouette score over k from 3 to 8 is
0.442, 0.469, 0.441, 0.436, 0.438, 0.413, so four is the best of them, and the
differences are small enough that this is choosing the least bad k rather than
discovering a true number of kinds of month. 005-A in study-geoai-algo-py found
the same shape of answer for a different subject and said so plainly; the
honest reading is that the world does not come in four kinds, and that four
cuts it somewhere useful.

The labels are read off the centres rather than decided in advance, and the
centres in the units they were measured in are:

    frozen       45.3%   rain   9.7 mm   demand   5.0 mm   -33.9 / -39.1 C
    cool         34.2%   rain  41.6 mm   demand  30.4 mm    -3.1 /  -8.8 C
    hot and dry  16.7%   rain  43.3 mm   demand 153.8 mm    26.4 /  15.8 C
    hot and wet   3.8%   rain 280.9 mm   demand  95.7 mm    22.4 /  16.1 C

The two hot types are the pair that made a classification worth having. They
sit at almost the same temperature and are told apart only by water: one gets a
third of the rain its air could evaporate, the other three times as much. On a
sequential ramp they would have been neighbouring shades.

The shares are of a sample that is four months of the whole globe, so "frozen"
being the largest is the winter hemisphere and the poles, not a claim about
where people live. A month is classified, not a place.
"""

from __future__ import annotations

import numpy as np

from ferspas_tile.climate_axes import standardise

# In the order they are read, sorted along the warmth axis. k-means numbers its
# clusters by wherever the seeds landed, and that number is not a meaning.
#
# The axis and the thermometer disagree at the top of this list. By temperature
# alone the dry hot type is the warmer of the two; the wet one comes out higher
# on the axis because the axis counts evaporative demand as well. Either order
# would be defensible and the axis is the one used, so that the order in the
# legend is the order of something the maps beside it also show.
LABELS = ("Frozen", "Cool", "Hot and dry", "Hot and wet")

# Standardised, in the order climate_axes.VARIABLES gives.
CENTRES = (
    (-0.418578, -0.604281, -0.901753, -0.914779),
    (0.078126, -0.188483, 0.320627, 0.367643),
    (0.105398, 1.830008, 1.491382, 1.410077),
    (3.806296, 0.879769, 1.332780, 1.421212),
)

_CENTRES = np.array(CENTRES)


def classify(stack: dict[str, np.ma.MaskedArray]) -> np.ma.MaskedArray:
    """Which of the frozen centres this month is nearest to, per pixel.

    Plain Euclidean distance on the standardised variables, because that is
    what k-means minimised when it placed the centres. Using anything else here
    would assign pixels to centres that were never fitted for them.
    """
    scores = standardise(stack)
    nearest = None
    best = None
    for index in range(len(_CENTRES)):
        distance = None
        for i, score in enumerate(scores):
            term = (score - _CENTRES[index, i]) ** 2
            distance = term if distance is None else distance + term
        if best is None:
            best, nearest = distance, np.ma.zeros(distance.shape)
        else:
            closer = distance < best
            nearest = np.ma.where(closer, float(index), nearest)
            best = np.ma.minimum(best, distance)
    # The mask has to survive: a pixel with no rainfall reading has no type,
    # and type 0 is a claim rather than an absence.
    return np.ma.masked_array(nearest, mask=np.ma.getmaskarray(best))
