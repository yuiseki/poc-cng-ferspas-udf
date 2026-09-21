"""Styling taken from the collection, not invented here.

Every FERSPAS collection carries a `renders` block: a 256-entry colormap, the
value range it is stretched over, the nodata value and a resampling method.
Reading it means a tile looks the way FAO renders the same layer, for any of
the 1921 collections, without anyone picking colours.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from . import STAC_API

Colormap = dict[int, tuple[int, int, int, int]]


@dataclass(frozen=True)
class RenderSpec:
    title: str
    colormap: Colormap | None
    rescale: tuple[float, float] | None
    nodata: float | None
    resampling: str
    unit: str | None

    @property
    def has_style(self) -> bool:
        return self.colormap is not None or self.rescale is not None


def _colormap(raw: Any) -> Colormap | None:
    """rio-tiler wants integer keys and RGBA tuples; the API sends strings."""
    if not isinstance(raw, dict) or not raw:
        return None
    out: Colormap = {}
    for key, value in raw.items():
        try:
            index = int(key)
        except (TypeError, ValueError):
            return None
        if not isinstance(value, (list, tuple)) or len(value) not in (3, 4):
            return None
        rgba = tuple(int(v) for v in value)
        out[index] = rgba if len(rgba) == 4 else (*rgba, 255)
    return out or None


def _rescale(raw: Any) -> tuple[float, float] | None:
    """`rescale` is a list of ranges, one per band; this server reads band 1."""
    if not raw:
        return None
    first = raw[0] if isinstance(raw[0], (list, tuple)) else raw
    if len(first) < 2:
        return None
    return (float(first[0]), float(first[1]))


def spec_from_collection(collection: dict[str, Any]) -> RenderSpec:
    render = ((collection.get("renders") or {}).get("data")) or {}
    bands = collection.get("bands") or []
    band = bands[0] if bands else {}
    nodata = render.get("nodata")
    if nodata is None:
        nodata = band.get("nodata")
    return RenderSpec(
        title=render.get("title") or collection.get("title") or collection.get("id", ""),
        colormap=_colormap(render.get("colormap")),
        rescale=_rescale(render.get("rescale")),
        nodata=float(nodata) if nodata is not None else None,
        resampling=render.get("resampling") or "nearest",
        unit=band.get("unit"),
    )


def fetch_spec(
    collection_id: str, api_root: str = STAC_API, timeout: float = 30.0
) -> RenderSpec:
    """Read one collection record from the FERSPAS API.

    This is the one thing not answerable from the parquet tables: they carry
    what a collection is, not how FAO draws it.
    """
    response = httpx.get(
        f"{api_root}/collections/{collection_id}",
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": "poc-cng-ferspas-udf"},
    )
    response.raise_for_status()
    return spec_from_collection(response.json())
