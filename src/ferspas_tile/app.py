"""The tile server.

    GET /tiles/{short_id}/{time}/{z}/{x}/{y}.png

One more path segment than an ordinary XYZ endpoint. Everything FERSPAS
publishes is a time series, so the moment belongs in the URL next to the tile
index: a viewer swaps one segment to scrub 47 years, and every frame stays its
own cacheable URL.
"""

from __future__ import annotations

from .config import configure_gdal

configure_gdal()  # must happen before rasterio is imported

import logging  # noqa: E402
from typing import Any  # noqa: E402

import duckdb  # noqa: E402
from fastapi import FastAPI, HTTPException, Query, Response  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from pathlib import Path  # noqa: E402
from rio_tiler.errors import TileOutsideBounds  # noqa: E402
from rio_tiler.io import Reader  # noqa: E402

from . import ITEMS_PARQUET, __version__  # noqa: E402
from .index import CollectionIndex, load_index, public_collections  # noqa: E402
from .render import RenderSpec, fetch_spec  # noqa: E402

logger = logging.getLogger("ferspas_tile")

VIEWER = Path(__file__).resolve().parent.parent.parent / "viewer"

app = FastAPI(title="ferspas-tile", version=__version__)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"]
)

# short_id -> index, built once per collection and kept for the process.
_indexes: dict[str, CollectionIndex] = {}
_specs: dict[str, RenderSpec] = {}
_collection_ids: dict[str, str] = {}
_connection = duckdb.connect()


def _collection_id(short_id: str) -> str:
    """Full API id for a short id, resolved once from the items table."""
    if short_id not in _collection_ids:
        row = _connection.execute(
            f"SELECT any_value(collection) FROM read_parquet('{ITEMS_PARQUET}')"
            " WHERE short_id = ?",
            [short_id],
        ).fetchone()
        if not row or not row[0]:
            raise HTTPException(404, f"unknown collection: {short_id}")
        _collection_ids[short_id] = row[0]
    return _collection_ids[short_id]


def _index(short_id: str, dims: dict[str, str]) -> CollectionIndex:
    key = short_id + "|" + ",".join(f"{k}={v}" for k, v in sorted(dims.items()))
    if key not in _indexes:
        try:
            _indexes[key] = load_index(
                short_id, dims=dims or None, connection=_connection
            )
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
    return _indexes[key]


def _spec(short_id: str) -> RenderSpec:
    if short_id not in _specs:
        _specs[short_id] = fetch_spec(_collection_id(short_id))
    return _specs[short_id]


def _dims(season: str | None, lct: str | None, crop: str | None) -> dict[str, str]:
    pinned = {"season": season, "lct": lct, "crop": crop}
    return {k: v for k, v in pinned.items() if v}


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "service": "ferspas-tile",
        "version": __version__,
        "description": (
            "XYZ + time raster tiles read straight from FERSPAS Cloud Optimized"
            " GeoTIFFs, picked per request from a GeoParquet index"
        ),
        "index": ITEMS_PARQUET,
        "endpoints": {
            "collections": "/collections",
            "timestamps": "/collections/{short_id}/timestamps",
            "tilejson": "/collections/{short_id}/{time}/tilejson.json",
            "tile": "/tiles/{short_id}/{time}/{z}/{x}/{y}.png",
            "viewer": "/viewer",
        },
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/collections")
def collections(limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    """Collections this server can serve, longest time series first."""
    rows = public_collections(limit=limit, connection=_connection)
    return {"count": len(rows), "collections": rows}


@app.get("/collections/{short_id}/timestamps")
def timestamps(
    short_id: str,
    season: str | None = None,
    lct: str | None = None,
    crop: str | None = None,
) -> dict[str, Any]:
    index = _index(short_id, _dims(season, lct, crop))
    spec = _spec(short_id)
    return {
        "short_id": short_id,
        "collection": _collection_id(short_id),
        "title": spec.title,
        "unit": spec.unit,
        "rescale": spec.rescale,
        "dimensions": index.dims,
        "count": len(index),
        "first": index.times[0],
        "last": index.times[-1],
        "timestamps": index.times,
    }


@app.get("/collections/{short_id}/colormap")
def colormap(short_id: str) -> dict[str, Any]:
    """The collection's own colour ramp, so a legend matches the tiles."""
    spec = _spec(short_id)
    return {
        "short_id": short_id,
        "title": spec.title,
        "unit": spec.unit,
        "rescale": spec.rescale,
        "colormap": spec.colormap,
    }


@app.get("/collections/{short_id}/{time}/tilejson.json")
def tilejson(
    short_id: str,
    time: str,
    season: str | None = None,
    lct: str | None = None,
    crop: str | None = None,
) -> dict[str, Any]:
    index = _index(short_id, _dims(season, lct, crop))
    frame = index.frame(time)
    if frame is None:
        raise HTTPException(404, f"{short_id} has no frame at {time}")
    spec = _spec(short_id)
    return {
        "tilejson": "2.2.0",
        "name": f"{spec.title} {time}",
        "description": spec.unit or "",
        "tiles": [f"/tiles/{short_id}/{time}/{{z}}/{{x}}/{{y}}.png"],
        "minzoom": 0,
        "maxzoom": 8,
        "bounds": [-180, -90, 180, 90],
        "source": frame.href,
    }


@app.get("/tiles/{short_id}/{time}/{z}/{x}/{y}.png")
def tile(
    short_id: str,
    time: str,
    z: int,
    x: int,
    y: int,
    season: str | None = None,
    lct: str | None = None,
    crop: str | None = None,
) -> Response:
    index = _index(short_id, _dims(season, lct, crop))
    frame = index.frame(time)
    if frame is None:
        raise HTTPException(
            404,
            f"{short_id} has no frame at {time};"
            f" it runs {index.times[0]} to {index.times[-1]}",
        )
    spec = _spec(short_id)

    try:
        with Reader(frame.vsi_href) as reader:
            image = reader.tile(x, y, z, nodata=spec.nodata, resampling_method="nearest")
    except TileOutsideBounds:
        # Empty rather than an error: a viewer asks for tiles it cannot know
        # are outside the layer.
        return Response(b"", status_code=204)
    except Exception as exc:  # the COG read is the part that fails in the wild
        logger.exception("tile read failed: %s", frame.href)
        raise HTTPException(502, f"could not read {frame.href}: {exc}") from exc

    if spec.rescale:
        image.rescale(in_range=((spec.rescale[0], spec.rescale[1]),))
    content = image.render(img_format="PNG", colormap=spec.colormap)
    return Response(
        content,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=86400",
            "X-Source-COG": frame.href,
        },
    )


@app.get("/viewer")
def viewer() -> FileResponse:
    return FileResponse(VIEWER / "index.html", media_type="text/html")
