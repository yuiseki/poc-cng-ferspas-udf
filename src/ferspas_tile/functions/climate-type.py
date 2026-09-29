"""Which of four kinds of month this is, by nearest frozen cluster centre."""

from __future__ import annotations

from typing import Any

import numpy as np

from ferspas_tile.analysis import CATEGORICAL, Analysis, Input
from ferspas_tile.climate_types import LABELS, classify


def compute(
    stack: dict[str, np.ma.MaskedArray], params: dict[str, Any]
) -> np.ma.MaskedArray:
    return classify(stack)


ANALYSIS = Analysis(
    id="climate-type",
    title="What kind of month this is",
    question="Which of four kinds of month is this place having?",
    explanation=(
        "The other maps here measure one thing and shade it from low to high."
        " This one does something different: it sorts every place into one of"
        " four kinds of month and gives each kind its own colour. The four were"
        " not chosen in advance. They were found by asking a clustering method"
        " to divide the world's months into groups by rainfall, evaporative"
        " demand and the day and night temperatures, and then reading off what"
        " each group turned out to be. The colours are deliberately unrelated"
        " to each other, because two types are not more or less than one"
        " another, they are simply different, and the legend is the only place"
        " that says which is which. The pair worth looking at is the two hot"
        " types: they are at nearly the same temperature and are told apart"
        " only by water, one getting a third of the rain its air could"
        " evaporate and the other three times as much."
    ),
    unit="type",
    inputs=(
        Input("AGERA5-PF-M", role="rain"),
        Input("AGERA5-ET0-M", role="demand"),
        Input("AGERA5-TMAX-AVG-M", role="tmax"),
        Input("AGERA5-TMIN-AVG-M", role="tmin"),
    ),
    compute=compute,
    rescale=(0.0, float(len(LABELS) - 1)),
    scale=CATEGORICAL,
    classes=LABELS,
    notes=(
        "k-means on the four standardised variables, fitted once over 1.86"
        " million pixels by scripts/fit_climate_types.py and frozen in"
        " climate_types.py, then applied per pixel as a nearest-centre lookup."
        " Four is the best k by silhouette over 3 to 8, at 0.469, but the"
        " scores across that whole range run from 0.413 to 0.469, so this is"
        " the least bad cut rather than a true number of kinds of month. What"
        " it classifies is a month and not a place: the same pixel changes type"
        " between January and July, which is the point of having a time axis"
        " on it. Koppen and the FAO/IIASA Agro-Ecological Zones answer the"
        " related question about places rather than months, using rules written"
        " by people instead of clusters found in the data."
    ),
)
