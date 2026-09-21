"""Which COG covers this request, answered from a GeoParquet index.

poc-cng-hotosm-imagery-tile asks a STAC API per tile, which is right when the
index lives server side. Here the index is a static 9.4 MB file, so one DuckDB
query per collection at startup beats one HTTP round trip per tile: a time
series is a small table, and the answer for a tile is then a dict lookup.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import duckdb

from . import COLLECTIONS_PARQUET, ITEMS_PARQUET

# Assets under this host need Google credentials; anonymous readers get a 302
# to a login page, so a tile server cannot use them.
AUTHENTICATED_HOST = "storage.cloud.google.com"


@dataclass(frozen=True)
class Frame:
    """One time step of a collection: the moment, and the COG that holds it."""

    time: str
    href: str
    file_size: int | None

    @property
    def vsi_href(self) -> str:
        return f"/vsicurl/{self.href}"


class CollectionIndex:
    def __init__(self, short_id: str, frames: list[Frame], dims: dict[str, str]):
        self.short_id = short_id
        self.frames = frames
        self.dims = dims
        self._by_time = {frame.time: frame for frame in frames}

    def __len__(self) -> int:
        return len(self.frames)

    @property
    def times(self) -> list[str]:
        return [frame.time for frame in self.frames]

    def frame(self, time: str) -> Frame | None:
        return self._by_time.get(time)

    def nearest(self, time: str) -> Frame | None:
        """The frame at or before ``time``; the first frame if none is."""
        if not self.frames:
            return None
        earlier = [f for f in self.frames if f.time <= time]
        return earlier[-1] if earlier else self.frames[0]


def _as_time(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    return str(value)[:10]


def default_dims(
    short_id: str,
    items_parquet: str = ITEMS_PARQUET,
    connection: duckdb.DuckDBPyConnection | None = None,
) -> dict[str, str]:
    """A pinning that exists, for a collection split by several dimensions.

    Picking the first value of each dimension independently is a cross-product
    guess and often names a combination nobody published: GAEZ has a future
    PERIOD and a historical SSP that never appear together. So this asks the
    data instead, and returns the combination with the most frames, which is
    both real and the longest time series to look at.
    """
    con = connection or duckdb.connect()
    rows = con.execute(
        f"SELECT dims, count(*) AS n FROM read_parquet('{items_parquet}')"
        " WHERE short_id = ? AND cardinality(dims) > 0"
        " GROUP BY dims ORDER BY n DESC, dims LIMIT 1",
        [short_id],
    ).fetchall()
    return dict(rows[0][0]) if rows else {}


def load_index(
    short_id: str,
    items_parquet: str = ITEMS_PARQUET,
    dims: dict[str, str] | None = None,
    connection: duckdb.DuckDBPyConnection | None = None,
) -> CollectionIndex:
    """Read every frame of one collection out of items.parquet.

    ``dims`` pins the categorical datacube dimensions a collection is split by,
    keyed by the dimension's own name: ``{"SEASON": "GS1", "LCT": "LC-C"}`` or
    ``{"CROP-RES02": "WHEA"}``.  Matching happens against the ``dims`` map in
    the table rather than a column, because only nine of the sixty-five
    dimensions have a column of their own and the rest would be unreachable.

    A collection that is split and is not pinned returns several COGs for the
    same instant, which is an error rather than an arbitrary pick.
    """
    con = connection or duckdb.connect()
    dims = dims or {}
    where = ["short_id = ?"]
    params: list[Any] = [short_id]
    for name, value in sorted(dims.items()):
        where.append("dims[?] = ?")
        params.extend([name, value])

    rows = con.execute(
        f"SELECT start_datetime, data_href, file_size"
        f" FROM read_parquet('{items_parquet}')"
        f" WHERE {' AND '.join(where)}"
        f" ORDER BY start_datetime",
        params,
    ).fetchall()
    if not rows:
        raise LookupError(f"no items for {short_id} with {dims}")

    frames: list[Frame] = []
    seen: dict[str, str] = {}
    for start, href, size in rows:
        time = _as_time(start)
        if time in seen and seen[time] != href:
            raise LookupError(
                f"{short_id} has more than one COG at {time}; pin its dimensions"
                f" (got {seen[time]} and {href})"
            )
        seen[time] = href
        if time not in {f.time for f in frames}:
            frames.append(Frame(time=time, href=href, file_size=size))
    return CollectionIndex(short_id, frames, dims)


def public_collections(
    collections_parquet: str = COLLECTIONS_PARQUET,
    items_parquet: str = ITEMS_PARQUET,
    limit: int = 200,
    connection: duckdb.DuckDBPyConnection | None = None,
) -> list[dict[str, Any]]:
    """Collections a tile server can actually serve, longest time series first.

    Collections whose assets sit behind Google sign-in are left out: they would
    look available and then fail on every tile.
    """
    con = connection or duckdb.connect()
    rows = con.execute(
        f"""
        SELECT i.short_id,
               any_value(i.catalog)            AS catalog,
               any_value(c.title)              AS title,
               any_value(c.unit)               AS unit,
               any_value(c.dimensions)         AS dimensions,
               count(*)                        AS frames,
               min(i.start_datetime)           AS first_time,
               max(i.start_datetime)           AS last_time
        FROM read_parquet('{items_parquet}') i
        JOIN read_parquet('{collections_parquet}') c ON c.id = i.collection
        WHERE i.data_href NOT LIKE '%{AUTHENTICATED_HOST}%'
        GROUP BY i.short_id
        HAVING frames > 1
        ORDER BY frames DESC
        LIMIT ?
        """,
        [limit],
    ).fetchall()
    return [
        {
            "short_id": r[0],
            "catalog": r[1],
            "title": r[2],
            "unit": r[3],
            "dimensions": list(r[4] or []),
            "frames": r[5],
            "first_time": _as_time(r[6]),
            "last_time": _as_time(r[7]),
        }
        for r in rows
    ]
