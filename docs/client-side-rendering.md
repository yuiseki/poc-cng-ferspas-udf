# Could the browser do this instead of the server?

Two ideas keep coming up, and both are worth writing down rather than
re-deciding later: render the values on the GPU from encoded tiles, or skip the
tile server entirely and read the COGs from the browser.

Measured 2026-09-21 against this deployment.

## 1. maplibre-gl-shader-layer

<https://github.com/geoblocks/maplibre-gl-shader-layer> (MIT, Camptocamp R&D,
npm `maplibre-gl-shader-layer@0.1.3`). A Three.js-backed custom layer for
MapLibre with per-tile uniforms. The interesting class is
`MultiChannelSeriesTiledLayer`:

- RGB channels encode a value rather than a colour, Terrain-RGB style but
  generalised: `value = offset + ((R*65536 + G*256 + B) * slope)`, over one,
  two or three channels. Alpha 0 is nodata.
- A *series* axis with interpolation between elements, which for us would be
  time.
- The colormap is applied in the fragment shader from a description, so it is
  a client-side decision.

It inverts what this server does. We compute a value and bake a colour into a
PNG; that approach ships the value and colours it in the browser.

What it would buy:

- The rescale becomes a control rather than a constant. `rescale=(-200, 200)`
  is currently a source change and a redeploy.
- `gdd?base_c=0` would not be a different tile. Today a parameter change is a
  new cache key and a full recompute.
- Months could interpolate, so playback would be smooth rather than stepped.
- One tile serves every colour scheme, so the cache is more reusable.

What it would cost:

- It depends on `maplibre-gl ^5.15.0` as a normal dependency, not a peer. This
  viewer is on v6, and v6 is not mentioned in the repository's issues.
- Three.js becomes a dependency, and the viewer stops being one HTML file
  loaded from a CDN and needs a bundler.
- Version 0.1.3, first published 2026-02.

Where it would *not* help: `water-balance` reads two collections. Doing that
subtraction in the browser means shipping two tiles instead of one.

A sane path, if it is ever wanted, is a second endpoint emitting value-encoded
tiles alongside the coloured ones, not a replacement.

## 2. Reading the COGs directly in the browser

Prior attempts: [study-maplibre-cog-protocol](https://github.com/yuiseki/study-maplibre-cog-protocol)
rejected `@geomatico/maplibre-cog-protocol` because it cannot reproject, and
UTM COGs land in the wrong place.
[poc-maplibre-cog-warp-protocol](https://github.com/yuiseki/poc-maplibre-cog-warp-protocol)
then built a browser-side warp behind `addProtocol` and got a full
nearest-neighbour tile out of a `EPSG:32630` COG.

So it is not impossible, and the hard part of it is already done once.

For FERSPAS in particular, two of the usual obstacles do not apply:

- **Projection.** The AgERA5 collections are already `EPSG:4326` on a regular
  0.1 degree grid, which is the case a reprojection-free protocol handles. No
  warp needed; the 4326 to 3857 mapping is a per-row latitude transform.
- **Structure.** They are tiled 256x256, LZW, with overviews `[2, 4, 8, 16]`,
  float32, nodata -9999. geotiff.js reads all of that, and the overviews mean a
  low zoom does not download the full raster.

The obstacle that does apply is CORS, and it is decisive:

```
$ curl -sI -H 'Origin: https://ferspas-udf.yuiseki.net' \
    https://storage.googleapis.com/fao-gismgr-c3s-data/.../C3S.AGERA5-PF-M.2026-07.tif
HTTP/2 200
accept-ranges: bytes
content-length: 6802113
                       <- no access-control-allow-origin
```

and from a real browser:

```
Access to fetch at 'https://storage.googleapis.com/fao-gismgr-c3s-data/...'
from origin 'http://127.0.0.1:8811' has been blocked by CORS policy:
No 'Access-Control-Allow-Origin' header is present on the requested resource.
```

The range requests work; the bucket simply does not allow a browser to make
them. The same is true of the `storage.cloud.google.com` bucket behind ASIS,
which additionally requires a Google login.

So for this catalogue the answer is not "the browser cannot do the maths". It
is "FAO's bucket will not talk to a browser". Reading these COGs client-side
needs a CORS policy on a bucket that is not ours, or a proxy that adds the
header, and a proxy that reads the whole COG is a worse tile server than the
one that already exists.

Where it *would* work is a catalogue whose host sets the header. That is the
question to ask of a dataset before reaching for a client-side protocol, and it
is one HEAD request.

## What this means here

Nothing changes. The tile server stays, because:

- the data host blocks the browser, and
- the analyses combine two collections, which the server should do once rather
  than every viewer doing it twice over.

The shader-layer idea is worth returning to for the *colouring*, which is the
part the server has no business owning. It is orthogonal to where the values
come from.
