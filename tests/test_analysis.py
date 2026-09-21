import numpy as np
import pytest

from ferspas_tile.analysis import KELVIN, shift
from ferspas_tile.functions import REGISTRY


def arr(*values):
    return np.ma.masked_array(np.array(values, dtype="float64"))


def run(analysis_id, stack, params=None):
    spec = REGISTRY[analysis_id]
    # The server always supplies the instant; a monthly total needs it.
    defaults = {"time": "2026-07-01"}
    defaults.update({p.name: p.default for p in spec.parameters})
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
    out = run(
        "water-balance",
        {"precipitation": arr(120.0, 20.0), "reference_et": arr(40.0, 90.0)},
    )
    assert out.tolist() == [80.0, -70.0]


def test_aridity_is_a_ratio_and_is_capped():
    out = run(
        "aridity", {"precipitation": arr(50.0, 900.0), "reference_et": arr(100.0, 30.0)}
    )
    assert out[0] == pytest.approx(0.5)
    # a monsoon month would otherwise be 30 and flatten the whole colour range
    assert out[1] == pytest.approx(2.0)


def test_aridity_masks_rather_than_dividing_by_zero():
    out = run("aridity", {"precipitation": arr(5.0), "reference_et": arr(0.0)})
    assert np.ma.getmaskarray(out)[0]


def test_gdd_accumulates_over_the_month_it_is_asked_for():
    from ferspas_tile.functions.gdd import days_in_month

    assert days_in_month("2026-07-01") == 31
    assert days_in_month("2026-02-15") == 28
    assert days_in_month("2024-02-01") == 29  # a leap year

    stack = {"tmax": arr(20 + KELVIN), "tmin": arr(10 + KELVIN)}   # mean 15 C
    july = run("gdd", stack, {"time": "2026-07-01"})
    february = run("gdd", stack, {"time": "2026-02-01"})
    assert july[0] == pytest.approx(5.0 * 31)
    assert february[0] == pytest.approx(5.0 * 28)


def test_gdd_converts_kelvin_and_never_goes_negative():
    # 20 C max, 10 C min -> mean 15 C -> 5 degree-days a day above base 10
    warm = run("gdd", {"tmax": arr(20 + KELVIN), "tmin": arr(10 + KELVIN)})
    assert warm[0] == pytest.approx(5.0 * 31)
    # a freezing month contributes nothing, it does not subtract growth
    cold = run("gdd", {"tmax": arr(2 + KELVIN), "tmin": arr(-8 + KELVIN)})
    assert cold[0] == pytest.approx(0.0)


def test_gdd_base_temperature_is_a_parameter():
    stack = {"tmax": arr(20 + KELVIN), "tmin": arr(10 + KELVIN)}
    assert run("gdd", stack, {"base_c": 0.0})[0] == pytest.approx(15.0 * 31)
    assert run("gdd", stack, {"base_c": 10.0})[0] == pytest.approx(5.0 * 31)


def test_diurnal_range_is_the_swing():
    out = run("diurnal-range", {"tmax": arr(300.0), "tmin": arr(288.0)})
    assert out[0] == pytest.approx(12.0)


def test_change_subtracts_the_earlier_frame():
    out = run("change", {"value": arr(70.0), "earlier": arr(100.0)})
    assert out[0] == pytest.approx(-30.0)


def test_a_masked_input_pixel_stays_masked_in_the_result():
    precipitation = np.ma.masked_array([50.0, 50.0], mask=[False, True])
    out = run("water-balance", {"precipitation": precipitation, "reference_et": arr(10.0, 10.0)})
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
            explanation=(
                "A placeholder explanation that is long enough to satisfy the"
                " rule that every analysis says what it is for in plain words."
            ),
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
            explanation=(
                "A placeholder explanation that is long enough to satisfy the"
                " rule that every analysis says what it is for in plain words."
            ),
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


def test_every_analysis_explains_itself_in_plain_words():
    for spec in REGISTRY.values():
        words = spec.explanation.split()
        assert len(words) >= 40, f"{spec.id}: too short to explain anything"
        assert spec.explanation.strip().endswith("."), spec.id


def test_every_analysis_reads_monthly_collections():
    # Daily is finer than this proof of concept needs, and a monthly aridity
    # ratio is the interval the index is actually defined over.
    for spec in REGISTRY.values():
        for source in spec.inputs:
            assert source.short_id.endswith("-M"), f"{spec.id} reads {source.short_id}"


# -- growing conditions ----------------------------------------------------


def warm_wet(tmean_c, rain_mm, et0_mm):
    """A stack where both inputs are uniform, for reasoning about one pixel."""
    return {
        "tmax": arr(tmean_c + KELVIN),
        "tmin": arr(tmean_c + KELVIN),
        "precipitation": arr(rain_mm),
        "reference_et": arr(et0_mm),
    }


def test_warm_and_wet_scores_full():
    # 25 C is 15 above base 10, past the point where warmth stops limiting;
    # rain at half of demand is the AEZ threshold for a growing day.
    out = run("growing-conditions", warm_wet(25.0, 60.0, 120.0))
    assert out[0] == pytest.approx(1.0)


def test_hot_but_dry_scores_low():
    out = run("growing-conditions", warm_wet(30.0, 6.0, 200.0))
    assert out[0] == pytest.approx(0.06, abs=0.01)


def test_wet_but_freezing_scores_zero():
    out = run("growing-conditions", warm_wet(-5.0, 200.0, 20.0))
    assert out[0] == pytest.approx(0.0)


def test_the_worse_of_the_two_decides_not_the_average():
    # Hot and dry, and cold and wet, must not be rated above a place that is
    # merely adequate at both. An average would do exactly that.
    hot_dry = run("growing-conditions", warm_wet(30.0, 5.0, 200.0))[0]
    cold_wet = run("growing-conditions", warm_wet(-5.0, 200.0, 20.0))[0]
    adequate = run("growing-conditions", warm_wet(15.0, 40.0, 120.0))[0]
    assert adequate > hot_dry
    assert adequate > cold_wet


def test_the_base_temperature_moves_the_warmth_half():
    stack = warm_wet(6.0, 100.0, 100.0)
    # 6 C grows nothing with a base of 10, but is fine for a base-0 crop.
    assert run("growing-conditions", stack, {"base_c": 10.0})[0] == pytest.approx(0.0)
    assert run("growing-conditions", stack, {"base_c": 0.0})[0] > 0.5


def test_a_frozen_month_answers_zero_rather_than_unknown():
    """Siberian winter: -35 C and a reference ET of 0.1 mm for the month.

    Guarding the division by masking made every such pixel missing, and a
    missing pixel draws as transparent, which through a light basemap reads as
    a high score. The answer is not unknown: nothing grows at -35 C. Where the
    air cannot evaporate anything, water is not the constraint, so moisture is
    full and warmth decides.
    """
    out = run(
        "growing-conditions",
        {
            "tmax": arr(239.81),
            "tmin": arr(236.59),
            "precipitation": arr(9.24),
            "reference_et": arr(0.103),
        },
    )
    assert not np.ma.getmaskarray(out)[0]
    assert out[0] == pytest.approx(0.0)


def test_negligible_demand_does_not_make_a_cold_place_look_plantable():
    frozen = run("growing-conditions", warm_wet(-20.0, 5.0, 0.2))[0]
    warm = run("growing-conditions", warm_wet(22.0, 60.0, 110.0))[0]
    assert frozen == pytest.approx(0.0)
    assert warm > frozen
