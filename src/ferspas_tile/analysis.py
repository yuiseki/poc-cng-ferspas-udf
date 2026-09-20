"""The shape of an analysis. The analyses themselves live in `functions/`.

This module holds only the vocabulary: what an input is, what a parameter is,
what an analysis declares, and the two colour scales it may choose between.
One file per analysis sits in `functions/`, named after its id.

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

Colour is a contract, not a per-analysis decision
-------------------------------------------------

A reader who learns one map should be able to read the next one. So there are
exactly two ramps and one rule for choosing between them.

* ``DIVERGING`` (RdBu) for a quantity with a meaningful neutral value, and only
  when the displayed range is symmetric around it. Blue is above the neutral,
  red below. Every one of these happens to be about water, so blue is always
  "more water than the neutral".
* ``SEQUENTIAL`` (viridis) for an unsigned magnitude. Dark is low, bright is
  high, for every such analysis, so brightness always means "more of whatever
  the legend names".

Hue encodes direction, never judgement. Red is not "bad": less rain than last
year is a problem in a drought and a relief in a flood, and a tile server does
not know which. Anything evaluative belongs in the legend text, not the ramp.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Callable

import numpy as np

# Kelvin at 0 degrees Celsius; AgERA5 temperatures are stored in K.
KELVIN = 273.15

# The only two ramps, and the only two colormap names an analysis may use.
DIVERGING = "diverging"
SEQUENTIAL = "sequential"
RAMPS = {DIVERGING: "rdbu", SEQUENTIAL: "viridis"}


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
    # Two or three sentences for someone who does not work in agriculture or
    # remote sensing: what is being subtracted from what, and what the picture
    # is for. The question above is the headline; this is the caption.
    explanation: str
    unit: str
    inputs: tuple[Input, ...]
    compute: Callable[[dict[str, np.ma.MaskedArray], dict[str, Any]], np.ma.MaskedArray]
    rescale: tuple[float, float]
    scale: str = SEQUENTIAL
    # The value the two colours meet at. Required for a diverging scale, and
    # the displayed range has to sit symmetrically around it, or the colour a
    # reader reads as "neutral" lands somewhere that means nothing.
    neutral: float | None = None
    parameters: tuple[Parameter, ...] = field(default_factory=tuple)
    notes: str = ""

    def __post_init__(self) -> None:
        if len(self.explanation.split()) < 20:
            raise ValueError(
                f"{self.id}: the explanation is too short to explain anything"
            )
        low, high = self.rescale
        if low >= high:
            raise ValueError(f"{self.id}: rescale must increase")
        if self.scale == DIVERGING:
            if self.neutral is None:
                raise ValueError(f"{self.id}: a diverging scale needs a neutral value")
            if abs((self.neutral - low) - (high - self.neutral)) > 1e-9:
                raise ValueError(
                    f"{self.id}: range {self.rescale} is not symmetric around"
                    f" {self.neutral}, so the neutral colour would be misplaced"
                )
        elif self.scale == SEQUENTIAL:
            if self.neutral is not None:
                raise ValueError(f"{self.id}: a sequential scale has no neutral value")
        else:
            raise ValueError(f"{self.id}: unknown scale {self.scale!r}")

    @property
    def colormap_name(self) -> str:
        return RAMPS[self.scale]

    def reading(self) -> str:
        """One line telling a reader what the colours mean here."""
        low, high = self.rescale
        if self.scale == DIVERGING:
            return (
                f"blue is above {self.neutral:g} {self.unit}, red below,"
                f" white at {self.neutral:g}; clipped at {low:g} and {high:g}"
            )
        return f"dark is {low:g} {self.unit}, bright is {high:g} and above"

    def describe(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "question": self.question,
            "explanation": self.explanation,
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
            "scale": self.scale,
            "neutral": self.neutral,
            "colormap": self.colormap_name,
            "reading": self.reading(),
            "notes": self.notes,
        }

def shift(time: str, days: int) -> str:
    """Move a YYYY-MM-DD string by whole days."""
    return (date.fromisoformat(time) + timedelta(days=days)).isoformat()
