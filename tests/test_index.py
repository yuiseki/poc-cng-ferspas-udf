import duckdb
import pytest

from ferspas_tile.index import Frame, CollectionIndex, load_index


@pytest.fixture
def items(tmp_path):
    """A tiny items table shaped like the published one."""
    path = tmp_path / "items.parquet"
    con = duckdb.connect()
    con.execute(
        f"""
        COPY (
          SELECT * FROM (VALUES
            ('ASI-D','GS1','LC-C',DATE '2026-01-01','https://x/a.tif',10),
            ('ASI-D','GS1','LC-C',DATE '2026-01-11','https://x/b.tif',11),
            ('ASI-D','GS2','LC-C',DATE '2026-01-01','https://x/c.tif',12),
            ('PF',   NULL, NULL,  DATE '2026-01-05','https://x/d.tif',13)
          ) t(short_id, season, lct, start_datetime, data_href, file_size)
        ) TO '{path}' (FORMAT PARQUET)
        """
    )
    con.close()
    return str(path)


def test_frame_builds_a_vsicurl_path():
    assert Frame("2026-01-01", "https://x/a.tif", 1).vsi_href == "/vsicurl/https://x/a.tif"


def test_load_index_returns_frames_in_time_order(items):
    index = load_index("ASI-D", items, dims={"season": "GS1", "lct": "LC-C"})
    assert index.times == ["2026-01-01", "2026-01-11"]
    assert index.frame("2026-01-11").href == "https://x/b.tif"


def test_an_unpinned_split_collection_is_an_error_not_a_guess(items):
    # ASI-D has one COG per season for 2026-01-01; picking one silently would
    # give a map that is right half the time.
    with pytest.raises(LookupError, match="more than one COG"):
        load_index("ASI-D", items)


def test_pinning_one_dimension_is_enough_when_it_disambiguates(items):
    index = load_index("ASI-D", items, dims={"season": "GS2"})
    assert index.times == ["2026-01-01"]
    assert index.frame("2026-01-01").href == "https://x/c.tif"


def test_missing_collection_raises(items):
    with pytest.raises(LookupError, match="no items"):
        load_index("NOPE", items)


def test_a_bad_dimension_name_is_rejected_before_it_reaches_sql(items):
    with pytest.raises(ValueError, match="dimension column"):
        load_index("ASI-D", items, dims={"season; DROP TABLE x": "GS1"})


def test_nearest_falls_back_to_the_frame_before():
    index = CollectionIndex(
        "x",
        [Frame("2026-01-01", "a", None), Frame("2026-01-11", "b", None)],
        {},
    )
    assert index.nearest("2026-01-05").time == "2026-01-01"
    assert index.nearest("2026-01-11").time == "2026-01-11"
    assert index.nearest("2030-01-01").time == "2026-01-11"
    # before the series starts, the first frame rather than nothing
    assert index.nearest("1900-01-01").time == "2026-01-01"


def test_frame_for_a_time_that_is_not_there_is_none():
    index = CollectionIndex("x", [Frame("2026-01-01", "a", None)], {})
    assert index.frame("2026-01-02") is None
