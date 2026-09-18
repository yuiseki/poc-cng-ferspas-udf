"""Process-wide GDAL settings, applied before rasterio is imported.

Two things here were measured, not guessed.

The PROJ database: a conda install on the host exports ``PROJ_DATA`` and
``GDAL_DATA`` pointing at its own share directories.  rasterio's wheel ships a
newer PROJ, and the mismatch makes even ``CRS.from_epsg(3857)`` fail with
"DATABASE.LAYOUT.VERSION.MINOR = 4 whereas a number >= 6 is expected".  Any
inherited value has to be dropped rather than trusted.

The HTTP settings: without them a single 256x256 tile out of a 3.6 MB COG took
between 5 and 28 seconds, because GDAL issued many small uncached range
requests.  With them the same tiles take 1 to 2 seconds cold and are free once
the block is in the VSI cache.
"""

from __future__ import annotations

import os

# Cleared: whatever the host exports for these is for a different PROJ/GDAL.
INHERITED_TO_DROP = ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA", "GDAL_DRIVER_PATH")

GDAL_SETTINGS = {
    # Do not list the bucket "directory" when opening one object.
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
    # One connection, many ranges.
    "GDAL_HTTP_MULTIPLEX": "YES",
    "GDAL_HTTP_VERSION": "2",
    "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
    # Keep fetched blocks so neighbouring tiles are free.
    "VSI_CACHE": "TRUE",
    "VSI_CACHE_SIZE": "536870912",
    "GDAL_CACHEMAX": "512",
    # Read the header in one go instead of discovering it byte by byte.
    "GDAL_INGESTED_BYTES_AT_OPEN": "32768",
}


def configure_gdal() -> None:
    for name in INHERITED_TO_DROP:
        os.environ.pop(name, None)
    for name, value in GDAL_SETTINGS.items():
        os.environ.setdefault(name, value)
