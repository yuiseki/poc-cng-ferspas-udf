import numpy as np
import pytest

from ferspas_tile.analysis import KELVIN, REGISTRY, shift


def arr(*values):
    return np.ma.masked_array(np.array(values, dtype="float64"))


def run(analysis_id, stack, params=None):
    spec = REGISTRY[analysis_id]
    defaults = {p.name: p.default for p in spec.parameters}
    defaults.update(params or {})
    return spec.compute(stack, defaults)


def test_every_registered_analysis_describes_itself():
    for key, spec in REGISTRY.items():
        assert spec.id == key
        described = spec.describe()
        assert described["question"].endswith("?")
        assert described["inputs"], f"{key} reads nothing"
        assert described["rescale"][0] < described["rescale"][1]


def test_water_balance_is_rain_minus_demand():
    out = run("water-balance", {"precipitation": arr(5.0, 1.0), "reference_et": arr(2.0, 4.0)})
    assert out.tolist() == [3.0, -3.0]


def test_aridity_is_a_ratio_and_is_capped():
    out = run("aridity", {"precipitation": arr(2.0, 100.0), "reference_et": arr(4.0, 1.0)})
    assert out[0] == pytest.approx(0.5)
    # a wet day would otherwise be 100 and flatten the whole colour range
    assert out[1] == pytest.approx(2.0)


def test_aridity_masks_rather_than_dividing_by_zero():
    out = run("aridity", {"precipitation": arr(5.0), "reference_et": arr(0.0)})
    assert np.ma.getmaskarray(out)[0]


def test_gdd_converts_kelvin_and_never_goes_negative():
    # 20 C max, 10 C min -> mean 15 C -> 5 degree-days above base 10
    warm = run("gdd", {"tmax": arr(20 + KELVIN), "tmin": arr(10 + KELVIN)})
    assert warm[0] == pytest.approx(5.0)
    # a freezing day contributes nothing, it does not subtract growth
    cold = run("gdd", {"tmax": arr(2 + KELVIN), "tmin": arr(-8 + KELVIN)})
    assert cold[0] == pytest.approx(0.0)


def test_gdd_base_temperature_is_a_parameter():
    stack = {"tmax": arr(20 + KELVIN), "tmin": arr(10 + KELVIN)}
    assert run("gdd", stack, {"base_c": 0.0})[0] == pytest.approx(15.0)
    assert run("gdd", stack, {"base_c": 10.0})[0] == pytest.approx(5.0)


def test_diurnal_range_is_the_swing():
    out = run("diurnal-range", {"tmax": arr(300.0), "tmin": arr(288.0)})
    assert out[0] == pytest.approx(12.0)


def test_change_subtracts_the_earlier_frame():
    out = run("change", {"value": arr(7.0), "earlier": arr(10.0)})
    assert out[0] == pytest.approx(-3.0)


def test_a_masked_input_pixel_stays_masked_in_the_result():
    precipitation = np.ma.masked_array([5.0, 5.0], mask=[False, True])
    out = run("water-balance", {"precipitation": precipitation, "reference_et": arr(1.0, 1.0)})
    assert not np.ma.getmaskarray(out)[0]
    assert np.ma.getmaskarray(out)[1]


def test_shift_moves_a_date_by_whole_days():
    assert shift("2026-03-01", -1) == "2026-02-28"
    assert shift("2026-01-01", -365) == "2025-01-01"
    assert shift("2026-08-01", 0) == "2026-08-01"


# -- the colour contract ---------------------------------------------------


def test_only_two_ramps_are_ever_used():
    """A reader who learns one map should be able to read the next one."""
    from ferspas_tile.analysis import RAMPS

    used = {spec.colormap_name for spec in REGISTRY.values()}
    assert used <= set(RAMPS.values())
    assert len(used) <= 2


def test_a_diverging_scale_is_symmetric_around_its_neutral():
    from ferspas_tile.analysis import DIVERGING

    for spec in REGISTRY.values():
        if spec.scale != DIVERGING:
            continue
        low, high = spec.rescale
        assert spec.neutral is not None, spec.id
        assert (spec.neutral - low) == pytest.approx(high - spec.neutral), spec.id


def test_a_sequential_scale_starts_at_its_low_end_and_has_no_neutral():
    from ferspas_tile.analysis import SEQUENTIAL

    for spec in REGISTRY.values():
        if spec.scale == SEQUENTIAL:
            assert spec.neutral is None, spec.id


def test_an_asymmetric_diverging_scale_is_refused():
    from ferspas_tile.analysis import DIVERGING, Analysis, Input

    with pytest.raises(ValueError, match="not symmetric"):
        Analysis(
            id="bad",
            title="bad",
            question="?",
            unit="x",
            inputs=(Input("A"),),
            compute=lambda stack, params: stack["value"],
            rescale=(-1.0, 10.0),
            scale=DIVERGING,
            neutral=0.0,
        )


def test_a_diverging_scale_without_a_neutral_is_refused():
    from ferspas_tile.analysis import DIVERGING, Analysis, Input

    with pytest.raises(ValueError, match="needs a neutral"):
        Analysis(
            id="bad",
            title="bad",
            question="?",
            unit="x",
            inputs=(Input("A"),),
            compute=lambda stack, params: stack["value"],
            rescale=(-1.0, 1.0),
            scale=DIVERGING,
        )


def test_every_analysis_states_how_to_read_its_colours():
    for spec in REGISTRY.values():
        reading = spec.reading()
        assert spec.unit in reading, spec.id
        # the words describe direction, never a verdict
        assert not any(word in reading.lower() for word in ("good", "bad")), spec.id
