"""Named analyses, each one an id plus the recipe for a tile.

The FAO demo notebooks each hard-coded one calculation over files on one
laptop: a difference between two years, a multi-year mean, a point validation.
The calculation was the interesting part and it was trapped in the notebook.

Here a calculation is a registry entry. It declares which FERSPAS collections
it reads, what parameters it takes and how its output should be coloured, and
the server turns it into `/analysis/{id}/{time}/{z}/{x}/{y}.png`. Adding an
analysis is adding one entry, not a new endpoint.

Every analysis works on a stack of aligned windows: the AgERA5 variables share
one 0.1 degree EPSG:4326 grid, so reading the same tile from several of them
gives arrays that line up pixel for pixel without any warping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Callable

import numpy as np

# Kelvin at 0 degrees Celsius; AgERA5 temperatures are stored in K.
KELVIN = 273.15


@dataclass(frozen=True)
class Input:
    """One collection an analysis reads, and at which offset in time."""

    short_id: str
    # Which frame relative to the requested one. 0 is the requested instant.
    # Anything else is resolved against the collection's own timestamps.
    offset_days: int = 0
    role: str = "value"


@dataclass(frozen=True)
class Parameter:
    name: str
    kind: str  # "int" | "float" | "date"
    default: Any
    description: str


@dataclass(frozen=True)
class Analysis:
    id: str
    title: str
    question: str
    unit: str
    inputs: tuple[Input, ...]
    compute: Callable[[dict[str, np.ma.MaskedArray], dict[str, Any]], np.ma.MaskedArray]
    rescale: tuple[float, float]
    colormap_name: str = "rdbu"
    parameters: tuple[Parameter, ...] = field(default_factory=tuple)
    notes: str = ""

    def describe(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "question": self.question,
            "unit": self.unit,
            "inputs": [
                {"collection": i.short_id, "role": i.role, "offset_days": i.offset_days}
                for i in self.inputs
            ],
            "parameters": [
                {
                    "name": p.name,
                    "type": p.kind,
                    "default": p.default,
                    "description": p.description,
                }
                for p in self.parameters
            ],
            "rescale": list(self.rescale),
            "colormap": self.colormap_name,
            "notes": self.notes,
        }


# -- the calculations ------------------------------------------------------


def _water_balance(
    stack: dict[str, np.ma.MaskedArray], params: dict[str, Any]
) -> np.ma.MaskedArray:
    """Rain minus what the atmosphere can evaporate.

    Positive means water is accumulating; negative means a crop is drawing on
    soil moisture or irrigation. This is the everyday agrometeorological view
    of whether a place is wet or dry, and it needs two variables at once, which
    is exactly what a single-collection tile server cannot do.
    """
    return stack["precipitation"] - stack["reference_et"]


def _growing_degree_days(
    stack: dict[str, np.ma.MaskedArray], params: dict[str, Any]
) -> np.ma.MaskedArray:
    """Heat available to a crop on one day, above a base temperature.

    Crops develop on accumulated warmth rather than on calendar days, so this
    is the unit growth stages are counted in. Base 10 C suits maize; 0 C suits
    wheat.
    """
    base = float(params.get("base_c", 10.0))
    tmax = stack["tmax"] - KELVIN
    tmin = stack["tmin"] - KELVIN
    mean = (tmax + tmin) / 2.0
    return np.ma.maximum(mean - base, 0.0)


def _diurnal_range(
    stack: dict[str, np.ma.MaskedArray], params: dict[str, Any]
) -> np.ma.MaskedArray:
    """How far the temperature swings in a day.

    A wide swing means clear skies and dry air; a narrow one means cloud or
    humidity. It is a cheap proxy for conditions a single variable hides.
    """
    return stack["tmax"] - stack["tmin"]


def _aridity(
    stack: dict[str, np.ma.MaskedArray], params: dict[str, Any]
) -> np.ma.MaskedArray:
    """Rain as a fraction of atmospheric demand, capped at 2.

    Below about 0.5 a place cannot meet crop water demand from rain alone.
    Unlike the plain difference this is comparable between a cool wet place and
    a hot wet one.
    """
    demand = stack["reference_et"]
    safe = np.ma.masked_less_equal(demand, 0.01)
    return np.ma.minimum(stack["precipitation"] / safe, 2.0)


def _change(
    stack: dict[str, np.ma.MaskedArray], params: dict[str, Any]
) -> np.ma.MaskedArray:
    """This instant minus an earlier one of the same variable.

    The generalised form of what Case5 of the FAO notebooks did by indexing a
    sorted file list, which quietly compares different years if a file appears.
    """
    return stack["value"] - stack["earlier"]


REGISTRY: dict[str, Analysis] = {}


def register(analysis: Analysis) -> Analysis:
    REGISTRY[analysis.id] = analysis
    return analysis


register(
    Analysis(
        id="water-balance",
        title="Water balance (P - ET0)",
        question="Is this place gaining or losing water today?",
        unit="mm/day",
        inputs=(
            Input("AGERA5-PF", role="precipitation"),
            Input("AGERA5-ET0", role="reference_et"),
        ),
        compute=_water_balance,
        rescale=(-10.0, 10.0),
        colormap_name="rdbu",
        notes=(
            "Blue is a surplus, red a deficit. Two collections read at the same"
            " instant on the same grid."
        ),
    )
)

register(
    Analysis(
        id="aridity",
        title="Aridity ratio (P / ET0)",
        question="Can rain alone meet the atmospheric demand here?",
        unit="ratio",
        inputs=(
            Input("AGERA5-PF", role="precipitation"),
            Input("AGERA5-ET0", role="reference_et"),
        ),
        compute=_aridity,
        rescale=(0.0, 2.0),
        colormap_name="rdbu",
        notes="Below 0.5 rain cannot meet demand. Capped at 2 so wet days stay readable.",
    )
)

register(
    Analysis(
        id="gdd",
        title="Growing degree days",
        question="How much heat did a crop get today?",
        unit="degree-days",
        inputs=(Input("AGERA5-TMAX", role="tmax"), Input("AGERA5-TMIN", role="tmin")),
        compute=_growing_degree_days,
        rescale=(0.0, 20.0),
        colormap_name="inferno",
        parameters=(
            Parameter(
                "base_c",
                "float",
                10.0,
                "Base temperature in Celsius. 10 suits maize, 0 suits wheat.",
            ),
        ),
        notes="AgERA5 temperatures are Kelvin; the conversion happens here.",
    )
)

register(
    Analysis(
        id="diurnal-range",
        title="Diurnal temperature range",
        question="How far did the temperature swing today?",
        unit="K",
        inputs=(Input("AGERA5-TMAX", role="tmax"), Input("AGERA5-TMIN", role="tmin")),
        compute=_diurnal_range,
        rescale=(0.0, 25.0),
        colormap_name="magma",
        notes="A wide swing means clear dry air, a narrow one cloud or humidity.",
    )
)

register(
    Analysis(
        id="change",
        title="Change against an earlier date",
        question="How does today compare with a year ago?",
        unit="same as input",
        inputs=(
            Input("AGERA5-PF", role="value"),
            Input("AGERA5-PF", offset_days=-365, role="earlier"),
        ),
        compute=_change,
        rescale=(-10.0, 10.0),
        colormap_name="rdbu",
        parameters=(
            Parameter(
                "offset_days",
                "int",
                -365,
                "How far back the comparison frame is, in days.",
            ),
        ),
        notes=(
            "The offset is resolved against the timestamps that exist, so a"
            " missing day steps to the nearest earlier frame rather than failing."
        ),
    )
)


def shift(time: str, days: int) -> str:
    """Move a YYYY-MM-DD string by whole days."""
    return (date.fromisoformat(time) + timedelta(days=days)).isoformat()
