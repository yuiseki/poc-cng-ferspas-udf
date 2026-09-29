"""One common scale for the four monthly variables, fitted once for the world.

Rainfall is in millimetres, temperature in degrees, and the two cannot be
added, compared or clustered until they are on a common scale. Putting them
there needs a mean, a spread and a covariance.

Those have to be the same for every tile. Fitting them per tile would give each
tile its own definition of an average month, and the seams would show the
moment the map was panned: the same pixel would change colour depending on
which tile it happened to fall in. So the fit is done once over the whole
world by `scripts/fit_climate_axes.py` and its output is pasted in below.

Everything here is the method borrowed from study-geoai-algo-py rather than any
of its numbers. That repository fits principal components to street survey
values over 250 m cells in Tokyo; these are fitted to four climate variables
over the world. What carries across is the discipline its 006-B asks for: an
axis fitted on one sample is only worth freezing if it survives on another.
It does. Fitted on January, April and July separately, the loadings agree to
0.02 and the explained variance to 0.01.
"""

from __future__ import annotations

import numpy as np

# The order every array here is in.
VARIABLES = ("rain", "demand", "tmax", "tmin")

# fitted on 1,864,232 pixels, 4 months at z=2
MEAN = (36.552734, 41.915650, -11.180816, -17.474546)
STD = (64.203656, 61.143559, 25.209657, 23.604087)

# The first two principal components, 73.5% and 20.9% of the variance, 94.4%
# together. Their signs are chosen rather than inherited: an eigenvector's sign
# is arbitrary and a map's is not, so the first axis points at warmer and the
# second at wetter.
#
# The first is almost equally the two temperatures and evaporative demand, with
# rainfall along for the ride: it is the warm-and-thirsty axis. The second is
# almost entirely rainfall against demand, and nearly orthogonal to warmth: it
# is the wet-or-dry axis, and it is the one worth having, because it separates
# two places at the same temperature that could not be farmed the same way.
WARMTH_AXIS = (0.311961, 0.502738, 0.571381, 0.568733)
WATER_AXIS = (0.913831, -0.389526, -0.099936, -0.056527)

# For the Mahalanobis distance, which asks how unusual a combination of the
# four is rather than how large any one of them is.
INVERSE_COVARIANCE = (
    (1.378045, 0.351236, 1.869824, -2.758283),
    (0.351236, 3.830512, -12.064805, 8.843027),
    (1.869824, -12.064805, 138.215855, -128.878423),
    (-2.758283, 8.843027, -128.878423, 123.514778),
)

_MEAN = np.array(MEAN)
_STD = np.array(STD)
_INVERSE = np.array(INVERSE_COVARIANCE)


def standardise(
    stack: dict[str, np.ma.MaskedArray],
) -> list[np.ma.MaskedArray]:
    """The four variables as scores against the fitted world average.

    `stack` carries Kelvin, because that is how AgERA5 stores temperature, and
    the fit was made in Celsius. The conversion happens here so that no
    analysis has to remember it.
    """
    from ferspas_tile.analysis import KELVIN

    raw = (
        stack["rain"],
        stack["demand"],
        stack["tmax"] - KELVIN,
        stack["tmin"] - KELVIN,
    )
    return [(value - _MEAN[i]) / _STD[i] for i, value in enumerate(raw)]


def project(stack: dict[str, np.ma.MaskedArray], axis) -> np.ma.MaskedArray:
    """Where this month sits along one fitted axis, in standard deviations."""
    scores = standardise(stack)
    total = scores[0] * axis[0]
    for i in range(1, len(axis)):
        total = total + scores[i] * axis[i]
    return total


def mahalanobis_squared(
    stack: dict[str, np.ma.MaskedArray],
) -> np.ma.MaskedArray:
    """How far this combination of four is from the usual one, squared.

    Distance rather than difference: a hot month is ordinary and a wet month is
    ordinary, and a hot wet month may still be a combination that hardly occurs
    anywhere. Dividing through by the covariance is what makes that visible,
    because it stops two variables that usually move together from counting
    twice.
    """
    scores = standardise(stack)
    total = None
    for i in range(len(scores)):
        for j in range(len(scores)):
            term = scores[i] * scores[j] * _INVERSE[i, j]
            total = term if total is None else total + term
    # Rounding can put a squared distance a hair below zero, and a negative
    # distance is not a small number, it is a wrong one.
    return np.ma.maximum(total, 0.0)
