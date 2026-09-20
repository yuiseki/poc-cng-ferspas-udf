"""The tile cache. The thing that must not happen is filling the disk."""

import os
import time

import pytest

from ferspas_tile.cache import SUFFIX, TileCache


def test_a_stored_tile_comes_back(tmp_path):
    cache = TileCache(tmp_path, max_bytes=1000)
    assert cache.get("a") is None
    assert cache.put("a", b"hello")
    assert cache.get("a") == b"hello"
    assert cache.stats.hits == 1
    assert cache.stats.misses == 1


def test_different_keys_do_not_collide(tmp_path):
    cache = TileCache(tmp_path, max_bytes=1000)
    cache.put("a", b"1")
    cache.put("b", b"2")
    assert cache.get("a") == b"1"
    assert cache.get("b") == b"2"


def test_the_budget_is_never_exceeded(tmp_path):
    cache = TileCache(tmp_path, max_bytes=500)
    for i in range(50):
        cache.put(f"tile-{i}", b"x" * 100)
        assert cache.total_bytes() <= 500, f"over budget after {i}"
    assert cache.stats.evictions > 0


def test_eviction_removes_the_least_recently_used(tmp_path):
    cache = TileCache(tmp_path, max_bytes=250)
    for key in ("a", "b"):
        cache.put(key, b"x" * 100)
        time.sleep(0.01)
    cache.get("a")  # a is now the more recently used of the two
    os.utime(cache.path_for("a"), None)
    time.sleep(0.01)

    cache.put("c", b"x" * 100)
    assert cache.get("b") is None
    assert cache.get("a") is not None
    assert cache.get("c") is not None


def test_a_tile_bigger_than_the_whole_budget_is_not_cached(tmp_path):
    # Evicting everything and still not fitting would be the worst outcome.
    cache = TileCache(tmp_path, max_bytes=100)
    cache.put("small", b"x" * 50)
    assert cache.put("huge", b"x" * 200) is False
    assert cache.get("huge") is None
    assert cache.get("small") is not None
    assert cache.stats.skipped_too_large == 1


def test_a_zero_or_negative_budget_is_refused(tmp_path):
    with pytest.raises(ValueError):
        TileCache(tmp_path, max_bytes=0)
    with pytest.raises(ValueError):
        TileCache(tmp_path, max_bytes=-1)


def test_only_files_the_cache_wrote_are_counted_or_deleted(tmp_path):
    cache = TileCache(tmp_path / "tiles", max_bytes=200)
    stranger = tmp_path / "tiles" / "IMPORTANT.txt"
    stranger.write_bytes(b"y" * 5000)

    for i in range(10):
        cache.put(f"t{i}", b"x" * 100)

    assert stranger.exists(), "the cache deleted a file it did not write"
    assert stranger.read_bytes() == b"y" * 5000
    # and it is not counted towards the budget either
    assert cache.total_bytes() <= 200


def test_clear_removes_only_tiles(tmp_path):
    cache = TileCache(tmp_path, max_bytes=1000)
    keep = tmp_path / "keep.txt"
    keep.write_text("keep me")
    cache.put("a", b"1")
    cache.put("b", b"2")
    assert cache.clear() == 2
    assert cache.total_bytes() == 0
    assert keep.exists()


def test_no_partial_file_is_left_behind(tmp_path):
    cache = TileCache(tmp_path, max_bytes=1000)
    cache.put("a", b"x" * 10)
    leftovers = [p for p in tmp_path.rglob("*") if p.is_file() and ".part" in p.name]
    assert leftovers == []
    tiles = [p for p in tmp_path.rglob(f"*{SUFFIX}") if p.is_file()]
    assert len(tiles) == 1


def test_describe_reports_usage_against_the_budget(tmp_path):
    cache = TileCache(tmp_path, max_bytes=1000)
    cache.put("a", b"x" * 250)
    info = cache.describe()
    assert info["used_bytes"] == 250
    assert info["max_bytes"] == 1000
    assert info["used_fraction"] == 0.25
    assert info["tiles"] == 1


def test_concurrent_writes_stay_within_the_budget(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    cache = TileCache(tmp_path, max_bytes=2000)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: cache.put(f"k{i}", b"x" * 200), range(200)))
    assert cache.total_bytes() <= 2000
