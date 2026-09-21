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
            ('ASI-D', MAP{{'SEASON':'GS1','LCT':'LC-C'}}, DATE '2026-01-01','https://x/a.tif',10),
            ('ASI-D', MAP{{'SEASON':'GS1','LCT':'LC-C'}}, DATE '2026-01-11','https://x/b.tif',11),
            ('ASI-D', MAP{{'SEASON':'GS2','LCT':'LC-C'}}, DATE '2026-01-01','https://x/c.tif',12),
            ('PF',    MAP{{}}::MAP(VARCHAR,VARCHAR),      DATE '2026-01-05','https://x/d.tif',13)
          ) t(short_id, dims, start_datetime, data_href, file_size)
        ) TO '{path}' (FORMAT PARQUET)
        """
    )
    con.close()
    return str(path)


def test_frame_builds_a_vsicurl_path():
    assert Frame("2026-01-01", "https://x/a.tif", 1).vsi_href == "/vsicurl/https://x/a.tif"


def test_load_index_returns_frames_in_time_order(items):
    index = load_index("ASI-D", items, dims={"SEASON": "GS1", "LCT": "LC-C"})
    assert index.times == ["2026-01-01", "2026-01-11"]
    assert index.frame("2026-01-11").href == "https://x/b.tif"


def test_an_unpinned_split_collection_is_an_error_not_a_guess(items):
    # ASI-D has one COG per season for 2026-01-01; picking one silently would
    # give a map that is right half the time.
    with pytest.raises(LookupError, match="more than one COG"):
        load_index("ASI-D", items)


def test_pinning_one_dimension_is_enough_when_it_disambiguates(items):
    index = load_index("ASI-D", items, dims={"SEASON": "GS2"})
    assert index.times == ["2026-01-01"]
    assert index.frame("2026-01-01").href == "https://x/c.tif"


def test_missing_collection_raises(items):
    with pytest.raises(LookupError, match="no items"):
        load_index("NOPE", items)


def test_a_dimension_name_is_a_bound_value_not_sql(items):
    # The name is matched against the dims map as a parameter, so a name that
    # looks like SQL is simply a name that matches nothing.
    with pytest.raises(LookupError, match="no items"):
        load_index("ASI-D", items, dims={"SEASON'; DROP TABLE x --": "GS1"})


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


# -- dimension pinning -----------------------------------------------------
#
# Reported from the live site: opening RES02-CYL failed with "more than one COG
# at 1970-01-01", because the index listed a collection split by five
# dimensions and linked to it without pinning any of them.


@pytest.fixture
def split(tmp_path):
    """A collection split by two dimensions, one combination commoner."""
    path = tmp_path / "items.parquet"
    con = duckdb.connect()
    con.execute(
        f"""
        COPY (
          SELECT * FROM (VALUES
            ('CYL', MAP{{'CROP':'ALFA','SSP':'HIST'}}, DATE '1970-01-01','https://x/a.tif',1),
            ('CYL', MAP{{'CROP':'ALFA','SSP':'HIST'}}, DATE '1971-01-01','https://x/b.tif',1),
            ('CYL', MAP{{'CROP':'WHEA','SSP':'HIST'}}, DATE '1970-01-01','https://x/c.tif',1),
            ('PLAIN', MAP{{}}::MAP(VARCHAR,VARCHAR), DATE '1970-01-01','https://x/d.tif',1)
          ) t(short_id, dims, start_datetime, data_href, file_size)
        ) TO '{path}' (FORMAT PARQUET)
        """
    )
    con.close()
    return str(path)


def test_an_unpinned_split_collection_still_refuses_to_guess(split):
    from ferspas_tile.index import load_index as load

    with pytest.raises(LookupError, match="more than one COG"):
        load("CYL", split)


def test_the_default_pinning_is_a_combination_that_exists(split):
    from ferspas_tile.index import default_dims

    # ALFA has two frames, WHEA one, so ALFA is both real and the longer run.
    assert default_dims("CYL", split) == {"CROP": "ALFA", "SSP": "HIST"}


def test_the_default_opens_the_collection(split):
    from ferspas_tile.index import default_dims, load_index as load

    index = load("CYL", split, dims=default_dims("CYL", split))
    assert index.times == ["1970-01-01", "1971-01-01"]


def test_a_collection_with_no_dimensions_needs_no_default(split):
    from ferspas_tile.index import default_dims

    assert default_dims("PLAIN", split) == {}


def test_a_dimension_name_with_a_hyphen_is_pinnable(tmp_path):
    # CROP-RES02 is not a valid identifier, so it can never be a column; the
    # pinning matches against the dims map instead.
    from ferspas_tile.index import load_index as load

    path = tmp_path / "i.parquet"
    con = duckdb.connect()
    con.execute(
        f"""COPY (SELECT * FROM (VALUES
              ('C', MAP{{'CROP-RES02':'WHEA'}}, DATE '1970-01-01','https://x/w.tif',1)
            ) t(short_id, dims, start_datetime, data_href, file_size))
            TO '{path}' (FORMAT PARQUET)"""
    )
    con.close()
    index = load("C", str(path), dims={"CROP-RES02": "WHEA"})
    assert index.frames[0].href.endswith("w.tif")
