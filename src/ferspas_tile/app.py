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
import os  # noqa: E402
import threading  # noqa: E402
from collections.abc import AsyncIterator  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402
from typing import Any  # noqa: E402

import duckdb  # noqa: E402
from fastapi import FastAPI, HTTPException, Query, Response  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import (  # noqa: E402
    FileResponse,
    HTMLResponse,
    RedirectResponse,
)
from pathlib import Path  # noqa: E402
from rio_tiler.errors import TileOutsideBounds  # noqa: E402
from rio_tiler.io import Reader  # noqa: E402

import numpy as np  # noqa: E402
from rio_tiler.colormap import apply_cmap  # noqa: E402
from rio_tiler.colormap import cmap as default_colormaps  # noqa: E402
from rio_tiler.models import ImageData  # noqa: E402

from . import ITEMS_PARQUET, __version__  # noqa: E402
from .cache import TileCache  # noqa: E402
from .analysis import Analysis, shift  # noqa: E402
from .functions import REGISTRY  # noqa: E402
from .index import CollectionIndex, load_index, public_collections  # noqa: E402
from .render import RenderSpec, fetch_spec  # noqa: E402

logger = logging.getLogger("ferspas_tile")

VIEWER = Path(__file__).resolve().parent.parent.parent / "viewer"

# Rendered tiles are immutable: the COGs behind a past month do not change, so
# the same URL always produces the same bytes. The budget is what keeps this
# from being a way to fill the disk; both are overridable for a deployment that
# knows better than the default.
CACHE_DIR = Path(os.environ.get("FERSPAS_TILE_CACHE", "cache/tiles"))
CACHE_BYTES = int(os.environ.get("FERSPAS_TILE_CACHE_BYTES", 512 * 1024 * 1024))
tiles = TileCache(CACHE_DIR, max_bytes=CACHE_BYTES)

# An analysis reads its inputs in parallel, so these caches and the DuckDB
# connection are touched from several threads at once. A DuckDB connection is
# not safe to share that way: two concurrent queries on one connection returned
# no rows, which surfaced as a 404 that read exactly like "this date has no
# data". Every query takes its own cursor, and the memo dicts sit behind a lock.
_indexes: dict[str, CollectionIndex] = {}
_specs: dict[str, RenderSpec] = {}
_collection_ids: dict[str, str] = {}
_connection = duckdb.connect()
_cache_lock = threading.Lock()


def _query(sql: str, params: list[Any] | None = None) -> Any:
    """One statement on its own cursor, so threads do not share state."""
    return _connection.cursor().execute(sql, params or []).fetchall()


def _collection_id(short_id: str) -> str:
    """Full API id for a short id, resolved once from the items table."""
    with _cache_lock:
        if short_id in _collection_ids:
            return _collection_ids[short_id]
    rows = _query(
        f"SELECT any_value(collection) FROM read_parquet('{ITEMS_PARQUET}')"
        " WHERE short_id = ?",
        [short_id],
    )
    if not rows or not rows[0][0]:
        raise HTTPException(404, f"unknown collection: {short_id}")
    with _cache_lock:
        _collection_ids[short_id] = rows[0][0]
    return rows[0][0]


def _index(short_id: str, dims: dict[str, str]) -> CollectionIndex:
    key = short_id + "|" + ",".join(f"{k}={v}" for k, v in sorted(dims.items()))
    with _cache_lock:
        if key in _indexes:
            return _indexes[key]
    try:
        index = load_index(
            short_id, dims=dims or None, connection=_connection.cursor()
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    with _cache_lock:
        _indexes.setdefault(key, index)
        return _indexes[key]


def _spec(short_id: str) -> RenderSpec:
    with _cache_lock:
        if short_id in _specs:
            return _specs[short_id]
    spec = fetch_spec(_collection_id(short_id))
    with _cache_lock:
        _specs.setdefault(short_id, spec)
        return _specs[short_id]


def _dims(season: str | None, lct: str | None, crop: str | None) -> dict[str, str]:
    pinned = {"season": season, "lct": lct, "crop": crop}
    return {k: v for k, v in pinned.items() if v}


def warm_indexes() -> None:
    """Build the index for every collection the registry names, up front.

    Each index is one DuckDB query against a 9.4 MB remote parquet, about six
    seconds. Leaving them lazy meant the first visitor paid all of them at once:
    five analyses requested together right after boot took 55 seconds each, then
    4.5 seconds for every later cold date. Warming here moves that cost off the
    first request.
    """
    wanted = {source.short_id for spec in REGISTRY.values() for source in spec.inputs}

    def warm(short_id: str) -> str:
        try:
            _index(short_id, {})
            _spec(short_id)
            return short_id
        except Exception as exc:  # a warm-up failure must not stop the server
            logger.warning("could not warm %s: %s", short_id, exc)
            return short_id

    with ThreadPoolExecutor(max_workers=min(8, len(wanted) or 1)) as pool:
        list(pool.map(warm, sorted(wanted)))
    logger.info("warmed %d collection indexes", len(wanted))


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    warm_indexes()
    yield


app = FastAPI(title="ferspas-udf", version=__version__, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"]
)

# short_id -> index, built once per collection and kept for the process.
#


@app.get("/", response_class=HTMLResponse)
def home() -> FileResponse:
    """The index: every function, with what it answers and a link to its map."""
    return FileResponse(VIEWER / "home.html", media_type="text/html")


@app.get("/service.json")
def service() -> dict[str, Any]:
    return {
        "service": "ferspas-udf",
        "source": "https://github.com/yuiseki/poc-cng-ferspas-udf",
        "version": __version__,
        "description": (
            "XYZ + time raster tiles read straight from FERSPAS Cloud Optimized"
            " GeoTIFFs, picked per request from a GeoParquet index"
        ),
        "index": ITEMS_PARQUET,
        "endpoints": {
            "index": "/",
            "collections": "/collections",
            "timestamps": "/collections/{short_id}/timestamps",
            "tilejson": "/collections/{short_id}/{time}/tilejson.json",
            "tile": "/tiles/{short_id}/{time}/{z}/{x}/{y}.png",
            "analyses": "/analysis",
            "analysis_tile": "/analysis/{id}/{time}/{z}/{x}/{y}.png",
            "analysis_viewer": "/viewer/analysis/{id}",
            "collection_viewer": "/viewer/collection/{short_id}",
        },
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/cache")
def cache_status() -> dict[str, object]:
    """How much of the tile cache budget is in use."""
    return tiles.describe()


@app.get("/collections")
def collections(limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    """Collections this server can serve, longest time series first."""
    rows = public_collections(limit=limit, connection=_connection.cursor())
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
    key = f"tile|{short_id}|{season}|{lct}|{crop}|{time}|{z}/{x}/{y}"
    cached = tiles.get(key)
    if cached is not None:
        return Response(
            cached,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400", "X-Cache": "hit"},
        )

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
    tiles.put(key, content)
    return Response(
        content,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=86400",
            "X-Cache": "miss",
            "X-Source-COG": frame.href,
        },
    )


# -- analyses --------------------------------------------------------------


@app.get("/analysis")
def analyses() -> dict[str, Any]:
    """Every named analysis this server can render."""
    return {
        "count": len(REGISTRY),
        "analyses": [a.describe() for a in REGISTRY.values()],
    }


@app.get("/analysis/{analysis_id}")
def analysis_detail(analysis_id: str) -> dict[str, Any]:
    spec = REGISTRY.get(analysis_id)
    if spec is None:
        raise HTTPException(404, f"unknown analysis: {analysis_id}")
    described = spec.describe()
    index = _index(spec.inputs[0].short_id, {})
    described["timestamps"] = {
        "count": len(index),
        "first": index.times[0],
        "last": index.times[-1],
    }
    described["tiles"] = f"/analysis/{analysis_id}/{{time}}/{{z}}/{{x}}/{{y}}.png"
    return described


def _read_window(short_id: str, time: str, z: int, x: int, y: int) -> Any:
    """One tile-shaped window of one collection, as a masked array.

    Returns None when the tile lies outside the layer, which the caller turns
    into an empty response rather than a coloured square of nothing.
    """
    index = _index(short_id, {})
    frame = index.frame(time) or index.nearest(time)
    if frame is None:
        raise HTTPException(404, f"{short_id} has no frame near {time}")
    spec = _spec(short_id)
    try:
        with Reader(frame.vsi_href) as reader:
            image = reader.tile(x, y, z, nodata=spec.nodata, resampling_method="nearest")
    except TileOutsideBounds:
        return None, frame
    except Exception as exc:
        logger.exception("analysis read failed: %s", frame.href)
        raise HTTPException(502, f"could not read {frame.href}: {exc}") from exc
    band = image.data[0].astype("float64")
    mask = image.array.mask[0] if hasattr(image.array, "mask") else None
    return np.ma.masked_array(band, mask=mask), frame


@app.get("/analysis/{analysis_id}/{time}/{z}/{x}/{y}.png")
def analysis_tile(
    analysis_id: str,
    time: str,
    z: int,
    x: int,
    y: int,
    base_c: float | None = None,
    offset_days: int | None = None,
) -> Response:
    spec: Analysis | None = REGISTRY.get(analysis_id)
    if spec is None:
        raise HTTPException(404, f"unknown analysis: {analysis_id}")

    # Parameters are part of the key: the same tile with a different base
    # temperature is a different picture.
    key = f"analysis|{analysis_id}|{time}|{z}/{x}/{y}|{base_c}|{offset_days}"
    cached = tiles.get(key)
    if cached is not None:
        return Response(
            cached,
            media_type="image/png",
            headers={
                "Cache-Control": "public, max-age=86400",
                "X-Analysis": analysis_id,
                "X-Cache": "hit",
            },
        )

    # The instant is always available to a calculation: a monthly total needs
    # to know how many days the month had.
    params: dict[str, Any] = {"time": time}
    params.update({p.name: p.default for p in spec.parameters})
    if base_c is not None:
        params["base_c"] = base_c
    if offset_days is not None:
        params["offset_days"] = offset_days

    def read(source: Any) -> tuple[str, Any, Any]:
        offset = source.offset_days
        if source.role == "earlier" and "offset_days" in params:
            offset = int(params["offset_days"])
        at = shift(time, offset) if offset else time
        window, frame = _read_window(source.short_id, at, z, x, y)
        return source.role, window, frame

    # The inputs are independent objects over HTTP, so opening them one after
    # another pays the connect-and-header cost twice in series. Cold, that is
    # the whole latency: measured 6.3 s serial against 3.4 s in parallel.
    stack: dict[str, np.ma.MaskedArray] = {}
    sources: list[str] = []
    with ThreadPoolExecutor(max_workers=len(spec.inputs)) as pool:
        for role, window, frame in pool.map(read, spec.inputs):
            if window is None:
                return Response(b"", status_code=204)
            stack[role] = window
            sources.append(frame.href)

    result = spec.compute(stack, params)
    low, high = spec.rescale
    # Stretch the physical range onto the 256 entries of the colour table.
    # Values outside it clamp rather than wrap, so an extreme day reads as
    # "at least this much" instead of looking like its opposite.
    scaled = np.clip((result - low) / (high - low), 0.0, 1.0)
    indexed = np.ma.filled(scaled, 0.0) * 255.0
    indexed = indexed.astype("uint8")[None, ...]

    table = default_colormaps.get(spec.colormap_name)
    coloured, _ = apply_cmap(indexed, table)
    # Pixels with no data in any input stay transparent.
    alpha = np.where(np.ma.getmaskarray(result), 0, 255).astype("uint8")
    rgba = np.concatenate([coloured, alpha[None, ...]], axis=0)

    image = ImageData(rgba)
    content = image.render(img_format="PNG", add_mask=False)

    tiles.put(key, content)
    return Response(
        content,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=86400",
            "X-Analysis": analysis_id,
            "X-Cache": "miss",
            "X-Source-COGs": ", ".join(sources),
        },
    )


# -- viewers ---------------------------------------------------------------
#
# One page per function rather than one page with a picker: a map of a named
# thing should have a URL you can send someone. Both routes serve the same
# file, which reads its target out of the path.


@app.get("/viewer/analysis/{analysis_id}", response_class=HTMLResponse)
def analysis_viewer(analysis_id: str) -> FileResponse:
    if analysis_id not in REGISTRY:
        raise HTTPException(404, f"unknown analysis: {analysis_id}")
    return FileResponse(VIEWER / "map.html", media_type="text/html")


@app.get("/viewer/collection/{short_id}", response_class=HTMLResponse)
def collection_viewer(short_id: str) -> FileResponse:
    _collection_id(short_id)  # 404 here rather than in the browser
    return FileResponse(VIEWER / "map.html", media_type="text/html")


@app.get("/viewer")
def viewer_redirect() -> RedirectResponse:
    return RedirectResponse("/", status_code=308)
