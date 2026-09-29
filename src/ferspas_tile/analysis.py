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
  red below, always, whatever the quantity is. This used to say that every
  diverging analysis happened to be about water, so that blue always meant more
  water. That stopped being true when an analysis of warmth arrived, and the
  rule that survived is the weaker and more honest one: blue is more of
  whatever the legend names, and the legend always names it.
* ``SEQUENTIAL`` (viridis) for an unsigned magnitude. Dark is low, bright is
  high, for every such analysis, so brightness always means "more of whatever
  the legend names".
* ``CATEGORICAL`` for a classification, where the output is a class number and
  nothing in between two of them means anything. Neither ramp can carry that:
  on either of them two adjacent class numbers come out nearly the same colour,
  so types that are not alike look alike. The palette is a fixed, colourblind
  safe sequence assigned in the order the analysis lists its classes, which
  keeps colour a contract rather than a per-analysis decision.

  The cost is worth naming. On a categorical map hue means "a different type"
  and nothing else. It does not mean colder, or more, or worse, so the legend
  is required reading in a way it is not on the other two. The classes are
  listed in a deliberate order rather than the order a clustering happened to
  number them, and that order is the only ranking in the map.

Hue encodes direction, never judgement. Red is not "bad": less rain than last
year is a problem in a drought and a relief in a flood, and a tile server does
not know which. Anything evaluative belongs in the legend text, not the ramp.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Callable

import numpy as np

# Kelvin at 0 degrees Celsius; AgERA5 temperatures are stored in K.
KELVIN = 273.15

# The only two ramps, and the only two colormap names an analysis may use.
DIVERGING = "diverging"
SEQUENTIAL = "sequential"
CATEGORICAL = "categorical"
RAMPS = {DIVERGING: "rdbu", SEQUENTIAL: "viridis"}

# Okabe and Ito's qualitative palette, reordered to open on a blue and to keep
# a red and a green from ever sitting next to each other. It is designed so
# that no two entries collapse into one another for a colourblind reader, and
# so that none of them reads as ranked above another.
PALETTE = (
    (0, 114, 178),    # blue
    (230, 159, 0),    # orange
    (0, 158, 115),    # bluish green
    (204, 121, 167),  # reddish purple
    (86, 180, 233),   # sky blue
    (213, 94, 0),     # vermillion
    (240, 228, 66),   # yellow
    (153, 153, 153),  # grey
)


@dataclass(frozen=True)
class Input:
    """One collection an analysis reads, and at which offset in time."""

    short_id: str
    # Which frame relative to the requested one. 0 is the requested instant.
    # Anything else is resolved against the collection's own timestamps.
    offset_days: int = 0
    role: str = "value"
    # Whole calendar months back or forward, for anything that has to land on
    # the same calendar month of another year. Days cannot express that: leap
    # days accumulate, so -365 * 4 lands on the 31st of the month before, and
    # a reader comparing "the same July" would silently get June.
    offset_months: int = 0
    # The same calendar month of one fixed year, whatever year was asked for.
    # A baseline period is stated in calendar years ("1979 to 1998"), not as a
    # distance from the request, and an offset would slide with the request.
    at_year: int | None = None

    def __post_init__(self) -> None:
        if self.offset_days and self.offset_months:
            raise ValueError(
                f"{self.short_id}: give an offset in days or in months, not both"
            )
        if self.at_year is not None and (self.offset_days or self.offset_months):
            raise ValueError(
                f"{self.short_id}: at_year is absolute; it takes no offset"
            )

    def resolve(self, time: str) -> str:
        """The instant this input wants, given the instant that was asked for."""
        if self.at_year is not None:
            when = date.fromisoformat(time)
            return date(self.at_year, when.month, 1).isoformat()
        if self.offset_months:
            return shift_months(time, self.offset_months)
        if self.offset_days:
            return shift(time, self.offset_days)
        return time


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
    # For a categorical analysis: what class 0, 1, 2 and so on mean, in the
    # order they should be read. compute() returns the index into this.
    classes: tuple[str, ...] = ()
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
        elif self.scale == CATEGORICAL:
            if self.neutral is not None:
                raise ValueError(f"{self.id}: a categorical scale has no neutral value")
            if len(self.classes) < 2:
                raise ValueError(f"{self.id}: a classification needs classes to name")
            if len(self.classes) > len(PALETTE):
                raise ValueError(
                    f"{self.id}: {len(self.classes)} classes but the palette has"
                    f" {len(PALETTE)}, and a repeated colour is two types drawn"
                    f" as one"
                )
            if self.rescale != (0.0, float(len(self.classes) - 1)):
                raise ValueError(
                    f"{self.id}: rescale has to be the range of class numbers,"
                    f" (0.0, {float(len(self.classes) - 1)})"
                )
        else:
            raise ValueError(f"{self.id}: unknown scale {self.scale!r}")
        if self.classes and self.scale != CATEGORICAL:
            raise ValueError(f"{self.id}: only a categorical analysis has classes")

    @property
    def colormap_name(self) -> str | None:
        """The named ramp, or None for a classification, which has no ramp."""
        return RAMPS.get(self.scale)

    def palette(self) -> tuple[tuple[int, int, int], ...]:
        """One colour per class, in the order the classes are listed."""
        return PALETTE[: len(self.classes)]

    def reading(self) -> str:
        """One line telling a reader what the colours mean here."""
        low, high = self.rescale
        if self.scale == DIVERGING:
            return (
                f"blue is above {self.neutral:g} {self.unit}, red below,"
                f" white at {self.neutral:g}; clipped at {low:g} and {high:g}"
            )
        if self.scale == CATEGORICAL:
            return (
                "one colour per type, and the colours mean nothing but"
                " difference: " + ", ".join(self.classes)
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
                {
                    "collection": i.short_id,
                    "role": i.role,
                    "offset_days": i.offset_days,
                    "offset_months": i.offset_months,
                    "at_year": i.at_year,
                }
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
            "classes": list(self.classes),
            "palette": [list(c) for c in self.palette()],
            "colormap": self.colormap_name,
            "reading": self.reading(),
            "notes": self.notes,
        }

def shift(time: str, days: int) -> str:
    """Move a YYYY-MM-DD string by whole days."""
    return (date.fromisoformat(time) + timedelta(days=days)).isoformat()


def shift_months(time: str, months: int) -> str:
    """Move a YYYY-MM-DD string by whole calendar months.

    "The same month, twenty years ago" is not 7305 days ago. Leap days
    accumulate: four years of -365 lands on the 30th of the previous month, and
    twenty lands five days earlier still, so an analysis meant to compare two
    Julys quietly compares July with June. Frames here are monthly, and the
    index takes the frame at or before the instant, so that error is invisible
    in the output and wrong by a whole month.

    The day of the month is kept where the target month is long enough and
    clamped to its last day where it is not, so the 31st of a long month lands
    on the 28th or 29th of February rather than overflowing into March.
    """
    when = date.fromisoformat(time)
    total = (when.year * 12 + when.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    day = min(when.day, calendar.monthrange(year, month)[1])
    return date(year, month, day).isoformat()
