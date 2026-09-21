# poc-cng-ferspas-udf

> **A Cloud Native Geospatial PoC: named analysis functions over FAO FERSPAS,
> each one served as XYZ tiles with a time axis.** The function is the unit:
> one file declares what it reads, what it computes and how it is coloured, and
> becomes an endpoint. Nothing is pre-built; a tile is computed when asked for.

```
GET /tiles/{short_id}/{time}/{z}/{x}/{y}.png
```

One more path segment than an ordinary tile URL. Everything FERSPAS publishes is
a time series, so the moment belongs next to the tile index: a viewer swaps one
segment to scrub 47 years of global weather, and every frame stays its own
cacheable URL.

| | |
| --- | --- |
| live | <https://ferspas-udf.yuiseki.net/> |
| upstream data | [FAO FERSPAS](https://data.apps.fao.org/remote-sensing-portal/), 1921 collections / 639,947 COGs |
| index | <https://stac.yuiseki.net/fao-ferspas/items.parquet>, 9.4 MB |
| runtime | FastAPI + rio-tiler + DuckDB |
| example | <https://ferspas-udf.yuiseki.net/analysis/water-balance/2026-07-01/3/4/3.png> |

## Where this sits

[poc-cng-cog-tile](https://github.com/yuiseki/poc-cng-cog-tile) showed a FaaS
function can serve tiles from any COG without Martin's GoogleMapsCompatible
preprocessing.
[poc-cng-hotosm-imagery-tile](https://github.com/yuiseki/poc-cng-hotosm-imagery-tile)
replaced the fixed `COG_PATH` with a STAC API call per tile, so the function has
no preconfigured dataset.

This one changes two things.

The index is a static file, not an API. FERSPAS has a STAC API, but its item
metadata is also published as a 9.4 MB GeoParquet table, which was built for
this by surveying the catalogue and is served from
<https://stac.yuiseki.net/fao-ferspas/>. One DuckDB query at
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

A tile does not have to be a stored pixel. Each analysis is one file, named
after its id, declaring the collections it reads, its parameters and how its
output is coloured. The server turns it into a tile endpoint:

```
GET /analysis/{analysis_id}/{time}/{z}/{x}/{y}.png
```

```
src/ferspas_tile/
  analysis.py              the vocabulary: Input, Parameter, Analysis, the two scales
  functions/
    __init__.py            loads every sibling file, at import
    water-balance.py       -> /analysis/water-balance/...
    aridity.py
    gdd.py
    diurnal-range.py
    change.py
```

Adding an analysis is adding a file. It defines a `compute` function and an
`ANALYSIS`, and the loader picks it up; nothing registers it by hand. The
filename has to equal the id it declares, or loading fails, so a reader looking
for `water-balance` finds `water-balance.py`.

Ids contain hyphens, which no Python import statement accepts, so the files are
loaded from their paths rather than imported. That is the price of "the
filename is the id" and it seems worth paying.

A file that will not parse, or declares no `ANALYSIS`, or breaks the colour
contract, stops the server at import. None of those may turn into an analysis
that quietly is not there.

The FAO demo notebooks each hard-coded one calculation over files on one laptop
and the calculation stayed trapped there. Here it is a file.

| id | question | reads | unit |
| --- | --- | --- | --- |
| `water-balance` | Did this place gain or lose water this month? | PF-M, ET0-M | mm/month |
| `aridity` | Could rain alone keep a crop supplied this month? | PF-M, ET0-M | ratio |
| `gdd` | How much usable warmth did a crop get this month? | TMAX-AVG-M, TMIN-AVG-M | degree-days |
| `diurnal-range` | How far did the temperature swing between afternoon and night? | TMAX-AVG-M, TMIN-AVG-M | K |
| `change` | Was this month wetter or drier than the same month a year ago? | PF-M twice | mm/month |
| `growing-conditions` | Was this month both warm enough and wet enough to grow food? | TMAX-AVG-M, TMIN-AVG-M, PF-M, ET0-M | score |

Each analysis carries an `explanation`: a few sentences for someone who does
not work in agriculture or remote sensing, saying what is being subtracted from
what and what the picture is for. The index shows it on the card and the map
page shows it under the legend, and the constructor refuses an analysis whose
explanation is too short to explain anything.

### Monthly, not daily

The analyses read the monthly AgERA5 collections rather than the daily ones.
Daily is finer than this needs: at one frame a day a slider covers 16,997
frames and a year of scrubbing shows mostly weather, while at one a month it
covers 571 and shows seasons. It also matters to the arithmetic. An aridity
ratio over a single day mostly answers whether it happened to rain that day, so
the map came out almost entirely red; over a month it is the interval the index
is actually defined over. Growing degree days accumulate over the month, using
its real length, so February and July are not compared as if equal.

Why these five, for a reader who does not do agronomy:

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
- **Growing conditions** scores warmth and water separately and keeps the worse
  one, because a crop needs both and is stopped by whichever is missing. This
  is Liebig's law of the minimum, and taking a minimum rather than an average
  is the point: hot and bone dry has to score like wet and frozen, not like
  somewhere merely adequate at both.

`growing-conditions` is a simplification of the idea behind FAO and IIASA's
Agro-Ecological Zones, whose Length of Growing Period counts the days where
temperature and moisture both allow growth. The moisture threshold used here is
the AEZ one, rainfall over half of reference evapotranspiration. What is
missing is soil moisture storage and daily resolution. GAEZ's own answer is in
the same catalogue, as `RES01-LGD` in days per year, along with its thermal and
moisture yield constraint factors `RES02-FC1` and `RES02-FC2`; this server can
show those as raw collections.

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

The contract covers analyses, not raw values. `/tiles/...` renders a collection
with the colormap FERSPAS itself publishes in its `renders` block, so a raw
layer looks the way FAO draws it. That is the point of serving it: it is their
data and their cartography. The two ramps above are for numbers this server
computed, which upstream has no opinion about.

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
| `GET /` | the index: every function with what it answers |
| `GET /service.json` | the same thing for a machine |
| `GET /viewer/analysis/{id}` | map of one analysis |
| `GET /viewer/collection/{short_id}` | map of one raw collection |

A collection split by a categorical datacube dimension has more than one COG
per instant, and the server will not pick one silently. Name the dimension in
the query string to choose: `?SEASON=GS1&LCT=LC-C`, or `?CROP-RES02=WHEA`.
Matching is against the dimension's own name, so all sixty-five are reachable,
not only the nine that have a column in the index.

A viewer opened without a pinning gets one: the combination with the most
frames, which exists by construction. Picking the first value of each dimension
independently does not work, because it names cross-products nobody published.
GAEZ has a future PERIOD and a historical SSP that never occur together, so a
guess like that is a 404 rather than a map. `/collections/{short_id}/timestamps`
reports which pinning was used and every value each dimension takes.

## Run it

```bash
make install
make serve
open http://127.0.0.1:8811/
```

The index lists every analysis with the question it answers, its inputs, its
colour ramp and how to read it, then the raw collections with the longest time
series. Each entry links to its own map.

A cold analysis tile is two COG reads over HTTPS, several seconds, so the
viewer says when it is waiting. The date changes the instant it is asked for,
the map fades and a spinner appears until the tiles for that month have
arrived, and playback waits for each frame instead of advancing on a timer that
outruns it.

Each load carries an epoch, because a load that finishes after you have moved
on must not clear the indicator for the month that is still loading. Measured:
jump to an uncached month, jump again a second later, and the panel stays in
its loading state until the second month is drawn, not the first.

Stepping is debounced by 250 ms, so holding a key does not queue a load per
repeat. Deliberate steps a second apart do each fetch their month, which is
what was asked for; before the indicator existed, three such steps issued 80
tile requests across four months with nothing on screen to say why the map had
not changed.

There are three ways to move through time, because a phone has none of the
keyboard and a slider thumb is not a touch target: buttons either side of
`play`, the slider, and the left and right arrow keys. The buttons are 44 px
and disable themselves at the ends of the series. On a narrow screen the
explanation folds behind a summary, because the panel is otherwise most of the
screen and the map is the point.

Left and right step through time from anywhere on the page, and the slider
takes keyboard focus as usual. Two things compete for those keys: the range
input handles them natively when focused, so that case is left alone rather
than stepping twice, and MapLibre pans the map with them once the canvas has
focus, so the handler listens in the capture phase and stops the event. After
clicking the map to look at something, the arrows still move time rather than
the map. Any hand on the slider, by drag or by key, stops playback.

Every map is its own URL, so one can be sent to someone:
`/viewer/analysis/water-balance` rather than a page plus instructions about
which item to pick from a dropdown. The map page reads its target out of the
path and carries a link back to the index. An id that does not exist is a 404
from the server rather than a page that loads and then fails in the browser.

## Tile cache

A rendered tile is expensive and immutable: the COGs behind a past month do not
change, so the same URL always produces the same bytes. They are cached to disk,
and a cold tile at about 4 s becomes 1 ms.

The one way this goes badly wrong is filling the disk, so the budget is a byte
count enforced on the way in, not a file count, a time-to-live, or a sweeper
that might not run. A write that would exceed it evicts least-recently-used
entries until it fits. A tile larger than the whole budget is not cached at
all, rather than evicting everything and still not fitting.

```bash
FERSPAS_TILE_CACHE=cache/tiles          # where
FERSPAS_TILE_CACHE_BYTES=536870912      # how much, default 512 MB
```

`GET /cache` reports usage against the budget, and responses carry
`X-Cache: hit` or `miss`. Only files the cache wrote are ever counted or
deleted; a stranger's file in the cache directory is left alone, which is
checked by a test. Tiles are written to a temporary name and renamed, so a
crash leaves no truncated entry and a reader never sees a half-written tile.

Verified rather than assumed: run with a 200 kB budget and asked for eight
tiles, the directory measured 195,825 bytes on disk with four evictions.

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

## Licence

MIT. See `LICENSE`.

The data is FAO's, not this repository's. Nothing here redistributes a raster:
tiles are rendered on request and the files stay on FAO's servers. Each FERSPAS
collection carries its own licence, and 291 of the 1921 are non-commercial, so
check the `license` column in `collections.parquet` before building on a
particular one.
