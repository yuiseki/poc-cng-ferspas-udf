# poc-cng-ferspas-test-tile

> **A Cloud Native Geospatial PoC: XYZ tiles with a time axis, read on the fly
> from FAO FERSPAS Cloud Optimized GeoTIFFs, picked per request from a
> GeoParquet index.** No tile pre-build, no preprocessed COG, no tile database.

```
GET /tiles/{short_id}/{time}/{z}/{x}/{y}.png
```

One more path segment than an ordinary tile URL. Everything FERSPAS publishes is
a time series, so the moment belongs next to the tile index: a viewer swaps one
segment to scrub 47 years of daily global weather, and every frame stays its own
cacheable URL.

| | |
| --- | --- |
| upstream data | [FAO FERSPAS](https://data.apps.fao.org/remote-sensing-portal/), 1921 collections / 639,947 COGs |
| index | <https://stac.yuiseki.net/fao-ferspas/items.parquet> (9.4 MB, built by [study-un-fao-ferspas](../../_study/study-un-fao-ferspas)) |
| runtime | FastAPI + rio-tiler + DuckDB |
| example | `/tiles/AGERA5-PF/2026-08-01/2/1/1.png` |

## Where this sits

[poc-cng-cog-tile](../poc-cng-cog-tile) showed a FaaS function can serve tiles
from any COG without Martin's GoogleMapsCompatible preprocessing.
[poc-cng-hotosm-imagery-tile](../poc-cng-hotosm-imagery-tile) replaced the fixed
`COG_PATH` with a STAC API call per tile, so the function has no preconfigured
dataset.

This one changes two things.

The index is a static file, not an API. FERSPAS has a STAC API, but its item
metadata is also published as a 9.4 MB GeoParquet table. One DuckDB query at
startup turns a whole collection into an in-memory time series, so answering
"which COG is this tile" costs a dict lookup rather than an HTTP round trip.
HOTOSM's per-tile `/search` is right when the index lives server side; here it
does not have to.

The request carries a time. HOTOSM imagery is "whatever exists here"; FERSPAS is
"this variable, on this day". So the URL names the instant and the server picks
the COG for it.

## Architecture

```
                              ┌────────────────────────────────────────┐
GET /tiles/AGERA5-PF/         │ ferspas-tile (FastAPI)                 │
    2026-08-01/{z}/{x}/{y}.png│                                        │
        │                     │  startup, once per collection:         │
        ▼                     │    DuckDB -> items.parquet             │ ──► stac.yuiseki.net
        │                     │    time -> COG href                    │
        │                     │    GET /collections/{id} -> renders     │ ──► data.apps.fao.org
        │                     │                                        │
        │                     │  per tile:                             │
        │                     │    1. time  -> href   (dict lookup)    │
        │                     │    2. rio-tiler /vsicurl/<cog>         │ ──► storage.googleapis.com
        │                     │       (window read, no warp, no copy)  │
        ▼                     │    3. rescale + the collection's own   │
    PNG                       │       256-entry colormap -> PNG        │
                              └────────────────────────────────────────┘
```

## Endpoints

| Path | Description |
| --- | --- |
| `GET /collections` | what this server can serve, longest time series first |
| `GET /collections/{short_id}/timestamps` | every instant that exists, and the unit and value range |
| `GET /collections/{short_id}/colormap` | the collection's own colour ramp, for a legend |
| `GET /collections/{short_id}/{time}/tilejson.json` | TileJSON for one instant |
| `GET /tiles/{short_id}/{time}/{z}/{x}/{y}.png` | the tile |
| `GET /viewer` | MapLibre viewer with a time slider |

Collections split by a categorical datacube dimension are pinned with query
parameters: `?season=GS1&lct=LC-C`. Without them such a collection has more than
one COG per instant, and the server says so instead of picking one.

## Run it

```bash
make install
make serve
open http://127.0.0.1:8811/viewer
```

## What was measured

**GDAL settings decide whether this is a tile server or a toy.** Untuned, a
single 256x256 tile out of a 3.6 MB COG took 5 to 28 seconds. With
`GDAL_DISABLE_READDIR_ON_OPEN`, HTTP/2 multiplexing, merged ranges and a VSI
cache it takes 1 to 2 seconds cold and is free once the block is cached. The
settings are in `config.py` with the numbers.

**Styling comes from the data.** Each FERSPAS collection ships a `renders` block
with a 256-entry colormap, a rescale range, the nodata value and a resampling
method. The server reads it, so a tile looks the way FAO draws the same layer,
for any collection, without anyone choosing colours.

**Not every collection can be served.** 20,163 of the 639,947 assets sit on
`storage.cloud.google.com`, which answers anonymous requests with a 302 to a
Google login page. That is all of ASIS, RDMS and one SEAP item. `/collections`
leaves them out rather than listing layers that fail on every tile.

**The time axis has holes.** AGERA5-PF claims 1979 to 2026 but has 16,997 frames,
not 17,397: 1979 has 290 days, 1980 has 328. A viewer has to step through the
timestamps the index reports, not through a calendar. `/timestamps` returns the
real list; `nearest()` exists for callers that have a date rather than a frame.

**A conda install on the host breaks rasterio.** `PROJ_DATA` and `GDAL_DATA`
exported by conda point at a PROJ database older than the one in rasterio's
wheel, and `CRS.from_epsg(3857)` fails at import time with
`DATABASE.LAYOUT.VERSION.MINOR = 4 whereas a number >= 6 is expected`. The
server drops those variables before importing rasterio.

**MapLibre v6 has no UMD build.** It is ESM only, has no default export, and
ships its worker as a separate file. Without `setWorkerUrl` the viewer renders
the basemap and never requests a tile.

## Not done

- No Knative manifest or container yet; this runs as a local process.
- No zoom limit tuning. AGERA5 is ~10 km, so past z8 the tiles are upsampled.
- The index is rebuilt at process start. A long-running deployment should watch
  the parquet's ETag instead.
