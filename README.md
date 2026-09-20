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

## Named analyses

A tile does not have to be a stored pixel. Each entry in `analysis.py` is an id,
the collections it reads, its parameters and how its output is coloured, and the
server turns it into a tile endpoint:

```
GET /analysis/{analysis_id}/{time}/{z}/{x}/{y}.png
```

The FAO demo notebooks each hard-coded one calculation over files on one laptop
and the calculation stayed trapped there. Here it is a registry entry, so adding
one is adding an entry rather than an endpoint.

| id | question | reads | unit |
| --- | --- | --- | --- |
| `water-balance` | Is this place gaining or losing water today? | PF, ET0 | mm/day |
| `aridity` | Can rain alone meet the atmospheric demand here? | PF, ET0 | ratio |
| `gdd` | How much heat did a crop get today? | TMAX, TMIN | degree-days |
| `diurnal-range` | How far did the temperature swing today? | TMAX, TMIN | K |
| `change` | How does today compare with a year ago? | PF twice | same as input |

Why these, for a reader who does not do agronomy:

- **Water balance** is rain minus what the atmosphere can evaporate. Positive
  means water is accumulating, negative means a crop is drawing on soil moisture
  or irrigation. It is the everyday agrometeorological view of wet and dry, and
  it needs two variables at once, which is exactly what a single-collection tile
  server cannot do.
- **Aridity** is the same pair as a ratio, so a cool wet place and a hot wet one
  are comparable. Below about 0.5 rain cannot meet crop demand.
- **Growing degree days** is the unit crop development is counted in: crops
  advance on accumulated warmth, not on calendar days. Base 10 C suits maize,
  0 C suits wheat, hence the parameter.
- **Diurnal range** is a cheap proxy for clear dry air against cloud or humidity.
- **Change** is the generalised form of what Case5 of the FAO notebooks did by
  indexing a sorted file list, which quietly compares different years if a file
  appears.

### Colour is a contract

A reader who learns one of these maps should be able to read the next one, so
the ramp is not a per-analysis decision. There are two, and one rule.

| scale | ramp | meaning |
| --- | --- | --- |
| `diverging` | RdBu | blue above the neutral value, red below, white at it |
| `sequential` | viridis | dark is the low end, bright the high end |

A diverging scale must declare its neutral value and its displayed range must
be symmetric around it, or the colour a reader takes as neutral lands somewhere
that means nothing. The constructor refuses the analysis otherwise, and a test
checks every registered one. `water-balance` and `change` are symmetric around
zero; `aridity` around one, where rain exactly equals demand.

Hue encodes direction, never judgement. Red is not "bad": less rain than last
year is a problem in a drought and a relief in a flood, and a tile server does
not know which. Anything evaluative belongs in the legend text. Every analysis
carries a `reading` line saying what its colours mean, which the viewer shows
next to the ramp.

This was got wrong first: `gdd` used inferno and `diurnal-range` used magma,
two different sequential ramps chosen for no reason, so the same brightness
meant different things on maps a reader would flip between.

Parameters ride as query strings: `?base_c=0` for a wheat-based GDD,
`?offset_days=-3650` to compare with ten years ago.

All the AgERA5 variables share one 0.1 degree EPSG:4326 grid, verified before
this was built, so reading the same tile from several of them gives arrays that
line up pixel for pixel with no warping.

FERSPAS already publishes some derived layers of its own, including CHIRPS
precipitation anomaly and Z-score. An analysis is worth adding here when it
combines collections that upstream does not combine, not when it duplicates a
layer that already exists.

## Endpoints

| Path | Description |
| --- | --- |
| `GET /collections` | what this server can serve, longest time series first |
| `GET /collections/{short_id}/timestamps` | every instant that exists, and the unit and value range |
| `GET /collections/{short_id}/colormap` | the collection's own colour ramp, for a legend |
| `GET /collections/{short_id}/{time}/tilejson.json` | TileJSON for one instant |
| `GET /tiles/{short_id}/{time}/{z}/{x}/{y}.png` | the tile |
| `GET /analysis` | the registry |
| `GET /analysis/{id}` | one analysis, its parameters and its time range |
| `GET /analysis/{id}/{time}/{z}/{x}/{y}.png` | a computed tile |
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

**An analysis costs about as much as its slowest input.** Cold, a two-input tile
took 6.3 s when the inputs were opened one after the other and 3.4 s when they
were opened in parallel; warm it is 20 ms. Nearly all of the cold time is the
TLS handshake and header read per COG, not the arithmetic.

**Reading inputs in parallel broke the index cache, quietly.** The DuckDB
connection was shared across threads, and two concurrent queries on one
connection returned no rows. That surfaced as a 404 reading exactly like "this
date has no data", intermittently. Every query now takes its own cursor and the
memo dicts sit behind a lock.

**Lazy indexes put the whole cost on the first visitor.** Each index is one
DuckDB query against the 9.4 MB remote parquet, about six seconds; five analyses
requested together just after boot took 55 s each. The server now warms the
indexes the registry names at startup, and a cold date costs about 4 s.

**MapLibre v6 has no UMD build.** It is ESM only, has no default export, and
ships its worker as a separate file. Without `setWorkerUrl` the viewer renders
the basemap and never requests a tile.

## Not done

- No Knative manifest or container yet; this runs as a local process.
- No zoom limit tuning. AGERA5 is ~10 km, so past z8 the tiles are upsampled.
- The index is rebuilt at process start. A long-running deployment should watch
  the parquet's ETag instead.
