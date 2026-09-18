from ferspas_tile.render import RenderSpec, spec_from_collection

COLLECTION = {
    "id": "fao-gismgr:C3S:raster:mapsets:AGERA5-PF",
    "title": "Precipitation flux",
    "bands": [{"name": "B1", "unit": "mm/day", "nodata": -9999.0}],
    "renders": {
        "data": {
            "title": "Precipitation Flux",
            "colormap": {"0": [230, 230, 230, 255], "255": [8, 104, 172, 255]},
            "rescale": [[0.0, 15.0]],
            "nodata": -9999.0,
            "resampling": "linear",
        }
    },
}


def test_spec_reads_the_collections_own_styling():
    spec = spec_from_collection(COLLECTION)
    assert spec.title == "Precipitation Flux"
    assert spec.rescale == (0.0, 15.0)
    assert spec.nodata == -9999.0
    assert spec.unit == "mm/day"
    assert spec.colormap[0] == (230, 230, 230, 255)
    assert spec.has_style


def test_colormap_keys_become_integers():
    spec = spec_from_collection(COLLECTION)
    assert all(isinstance(k, int) for k in spec.colormap)


def test_three_channel_colours_gain_full_alpha():
    collection = dict(COLLECTION)
    collection["renders"] = {"data": {"colormap": {"0": [1, 2, 3]}}}
    assert spec_from_collection(collection).colormap[0] == (1, 2, 3, 255)


def test_nodata_falls_back_to_the_band_when_renders_omits_it():
    collection = dict(COLLECTION)
    collection["renders"] = {"data": {"rescale": [[0, 1]]}}
    assert spec_from_collection(collection).nodata == -9999.0


def test_a_collection_without_renders_still_yields_a_spec():
    spec = spec_from_collection({"id": "x", "title": "Bare", "bands": []})
    assert isinstance(spec, RenderSpec)
    assert spec.colormap is None
    assert spec.rescale is None
    assert spec.resampling == "nearest"
    assert not spec.has_style


def test_a_malformed_colormap_is_dropped_rather_than_half_applied():
    collection = dict(COLLECTION)
    collection["renders"] = {"data": {"colormap": {"not-a-number": [1, 2, 3]}}}
    assert spec_from_collection(collection).colormap is None
