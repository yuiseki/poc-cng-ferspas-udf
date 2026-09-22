"""Heat stress on cattle, on one afternoon."""

from __future__ import annotations

from typing import Any

import numpy as np

from ferspas_tile.analysis import KELVIN, SEQUENTIAL, Analysis, Input

# The operational thresholds dairy advice is written against.
MILD = 72.0
MODERATE = 80.0
SEVERE = 90.0


def compute(
    stack: dict[str, np.ma.MaskedArray], params: dict[str, Any]
) -> np.ma.MaskedArray:
    """The NRC Temperature Humidity Index, from the day's maximum and 3 pm humidity.

        THI = (1.8 T + 32) - (0.55 - 0.0055 RH) (1.8 T - 26)

    T is in Celsius and RH in percent, so the temperature is converted out of
    Kelvin here and the humidity is used as it is stored. The first term is
    simply the temperature in Fahrenheit; the second is the relief evaporation
    gives, which shrinks to nothing as the air approaches saturation. That is
    why the index is not a temperature: 35 C in dry air is easier on an animal
    than 30 C in wet air, and a map of temperature alone says the opposite.
    """
    celsius = stack["tmax"] - KELVIN
    humidity = stack["humidity"]
    fahrenheit = 1.8 * celsius + 32.0
    return fahrenheit - (0.55 - 0.0055 * humidity) * (1.8 * celsius - 26.0)


ANALYSIS = Analysis(
    id="livestock-heat",
    title="Heat stress on cattle",
    question="How hard is this afternoon's heat on cattle here?",
    explanation=(
        "Animals lose heat by evaporating water, so how hard a hot day is on a"
        " cow depends on how humid the air is as well as how warm it is. This"
        " combines the day's highest temperature with the humidity in the middle"
        " of the afternoon, when both are at their worst, into the index dairy"
        " advice is written against. Bright means hard going. The thresholds"
        " that matter are 72, where milk yield starts to fall, 80, where intake"
        " and conception drop away, and 90, where animals are in danger. Nothing"
        " dies at 75, which is exactly why this is under-reported: the losses"
        " are in milk, fertility and feed intake, and they are invisible unless"
        " somebody is measuring."
    ),
    unit="index",
    inputs=(
        Input("AGERA5-TMAX", role="tmax"),
        Input("AGERA5-RH15", role="humidity"),
    ),
    compute=compute,
    rescale=(50.0, 90.0),
    scale=SEQUENTIAL,
    notes=(
        "The only analysis here that reads the daily collections rather than the"
        " monthly ones, and it has to: a month's average afternoon is not an"
        " afternoon, and heat stress is a thing that happens on particular days."
        " The cost is the time axis, which for this one analysis has 16,697"
        " frames rather than 571, so the slider steps a day at a time."
        " AGERA5-RH15 is relative humidity at 15:00 local, which is the closest"
        " the catalogue comes to the hottest part of the day. What the analyst"
        " asked for was a count of stress days per year weighted by cattle"
        " density; a day is what one tile request can read, and the cattle layer"
        " is not in this catalogue. Read the map as where cattle were under"
        " strain on that afternoon, not as where cattle are."
    ),
)
