"""An on-disk tile cache with a hard size budget.

A computed tile is expensive and immutable: the COGs behind a past month do not
change, so the same URL will always produce the same bytes. Caching them is
almost free to get right, except for the one way it goes badly wrong, which is
filling the disk.

So the budget is a byte count, not a file count or a time-to-live, and it is
enforced on the way in rather than by a sweeper that might not run. When a
write would take the cache over budget, the least recently used entries are
deleted until it fits. If a single tile is larger than the whole budget it is
simply not cached, rather than evicting everything and still not fitting.

Nothing outside the cache directory is ever touched, and only files this class
wrote are ever deleted.
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path

SUFFIX = ".tile"


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    writes: int = 0
    evictions: int = 0
    evicted_bytes: int = 0
    skipped_too_large: int = 0


class TileCache:
    def __init__(self, root: Path, max_bytes: int = 512 * 1024 * 1024) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self.root = Path(root)
        self.max_bytes = max_bytes
        self.root.mkdir(parents=True, exist_ok=True)
        self.stats = CacheStats()
        self._lock = threading.Lock()

    # -- keys ---------------------------------------------------------------
    def path_for(self, key: str) -> Path:
        """Two levels of fan-out so one directory never holds every tile."""
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.root / digest[:2] / f"{digest}{SUFFIX}"

    # -- reads and writes ---------------------------------------------------
    def get(self, key: str) -> bytes | None:
        path = self.path_for(key)
        try:
            data = path.read_bytes()
        except OSError:
            self.stats.misses += 1
            return None
        # Touch so eviction sees this as recently used. A failure here only
        # costs accuracy in the ordering, so it is not worth failing a request.
        try:
            os.utime(path, None)
        except OSError:
            pass
        self.stats.hits += 1
        return data

    def put(self, key: str, data: bytes) -> bool:
        """Store a tile, evicting older ones if it would not otherwise fit."""
        if len(data) > self.max_bytes:
            self.stats.skipped_too_large += 1
            return False
        path = self.path_for(key)
        with self._lock:
            self._make_room(len(data))
            path.parent.mkdir(parents=True, exist_ok=True)
            # Write beside the target and rename, so a reader never sees a
            # half-written tile and a crash leaves no truncated entry.
            temporary = path.with_suffix(f".{os.getpid()}.{time.time_ns()}.part")
            try:
                temporary.write_bytes(data)
                temporary.replace(path)
            except OSError:
                temporary.unlink(missing_ok=True)
                return False
            self.stats.writes += 1
        return True

    # -- housekeeping -------------------------------------------------------
    def entries(self) -> list[tuple[float, int, Path]]:
        """(mtime, size, path) for every tile this cache wrote."""
        found: list[tuple[float, int, Path]] = []
        for path in self.root.rglob(f"*{SUFFIX}"):
            try:
                stat = path.stat()
            except OSError:
                continue
            found.append((stat.st_mtime, stat.st_size, path))
        return found

    def total_bytes(self) -> int:
        return sum(size for _mtime, size, _path in self.entries())

    def _make_room(self, incoming: int) -> None:
        entries = self.entries()
        total = sum(size for _m, size, _p in entries)
        if total + incoming <= self.max_bytes:
            return
        entries.sort(key=lambda entry: entry[0])  # oldest touched first
        for _mtime, size, path in entries:
            if total + incoming <= self.max_bytes:
                break
            try:
                path.unlink()
            except OSError:
                continue
            total -= size
            self.stats.evictions += 1
            self.stats.evicted_bytes += size

    def describe(self) -> dict[str, object]:
        entries = self.entries()
        used = sum(size for _m, size, _p in entries)
        return {
            "root": str(self.root),
            "max_bytes": self.max_bytes,
            "used_bytes": used,
            "used_fraction": round(used / self.max_bytes, 4),
            "tiles": len(entries),
            "hits": self.stats.hits,
            "misses": self.stats.misses,
            "writes": self.stats.writes,
            "evictions": self.stats.evictions,
            "evicted_bytes": self.stats.evicted_bytes,
            "skipped_too_large": self.stats.skipped_too_large,
        }

    def clear(self) -> int:
        """Delete every tile. Only files this cache wrote are removed."""
        removed = 0
        with self._lock:
            for _mtime, _size, path in self.entries():
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    continue
        return removed
