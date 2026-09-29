import numpy as np
import pytest

from ferspas_tile.analysis import KELVIN, shift
from ferspas_tile.functions import REGISTRY, load_drafts

DRAFTS = load_drafts()
# The drafts are not served, but they are still analyses and the tests below
# were written against them. Everything that asks "is this a well formed
# analysis" runs over both; only the tests about what the server offers use
# REGISTRY alone.
ALL = {**REGISTRY, **DRAFTS}


def arr(*values):
    return np.ma.masked_array(np.array(values, dtype="float64"))


def run(analysis_id, stack, params=None):
    spec = ALL[analysis_id]
    # The server always supplies the instant; a monthly total needs it.
    defaults = {"time": "2026-07-01"}
    defaults.update({p.name: p.default for p in spec.parameters})
    defaults.update(params or {})
    return spec.compute(stack, defaults)


def test_no_draft_is_served():
    assert DRAFTS, "__draft/ is empty; drop the directory rather than leaving it"
    assert not set(REGISTRY) & set(DRAFTS)


def test_every_analysis_describes_itself():
    for key, spec in ALL.items():
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


# Daily is finer than most of this needs, and a monthly aridity ratio is the
# interval the index is actually defined over. The exception is named here
# rather than left to whoever adds the next analysis, and it is named with its
# reason: heat stress happens on an afternoon, and the average of thirty
# afternoons is not one.
DAILY_ANALYSES = {"livestock-heat"}


def test_every_analysis_reads_monthly_collections_unless_it_is_listed():
    for spec in ALL.values():
        if spec.id in DAILY_ANALYSES:
            continue
        for source in spec.inputs:
            assert source.short_id.endswith("-M"), f"{spec.id} reads {source.short_id}"


def test_an_analysis_that_reads_daily_frames_says_why_in_its_notes():
    for analysis_id in DAILY_ANALYSES:
        spec = REGISTRY[analysis_id]
        assert not any(i.short_id.endswith("-M") for i in spec.inputs), spec.id
        assert "daily" in spec.notes, spec.id


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


# -- the analyses that read many frames -------------------------------------
#
# Each of these is handed a stack keyed the way the server keys it, one entry
# per frame, newest first. The helpers below build one.


def stack_of(prefix, values):
    """One pixel per frame: {"y00": [v0], "y01": [v1], ...}."""
    return {f"{prefix}{k:02d}": arr(float(v)) for k, v in enumerate(values)}


def pixel(out):
    assert not np.ma.getmaskarray(out)[0], "the answer came back masked"
    return float(out[0])


# 1. month-percentile


def test_month_percentile_ranks_this_month_among_its_own_history():
    # this July is the wettest of eleven, so it sits at the top of the ramp
    wettest = stack_of("y", [300.0] + [10.0 * k for k in range(1, 11)])
    assert pixel(run("month-percentile", wettest)) == pytest.approx(
        100.0 * 10.5 / 11
    )
    # and the driest sits at the bottom, not at zero: it is one of the eleven
    driest = stack_of("y", [1.0] + [10.0 * k for k in range(1, 11)])
    assert pixel(run("month-percentile", driest)) == pytest.approx(100.0 * 0.5 / 11)


def test_month_percentile_puts_a_median_month_at_the_neutral_colour():
    # eleven years, five drier than this one and five wetter
    values = [50.0] + [float(v) for v in (10, 20, 30, 40, 45, 60, 70, 80, 90, 100)]
    assert pixel(run("month-percentile", stack_of("y", values))) == pytest.approx(50.0)


def test_month_percentile_needs_a_real_distribution_behind_it():
    """Six years is an anecdote, not a percentile, so it is left blank."""
    out = run("month-percentile", stack_of("y", [10.0] * 6))
    assert np.ma.getmaskarray(out)[0]


# 2. dependable-rainfall


def test_dependable_rainfall_is_the_one_year_in_five_amount():
    # 0, 10, 20 ... 100: the 20th percentile of eleven values is 20
    out = run("dependable-rainfall", stack_of("y", [10.0 * k for k in range(11)]))
    assert pixel(out) == pytest.approx(20.0)


def test_dependable_rainfall_is_below_the_average_in_a_variable_place():
    """The reason it is not the mean: a few wet years pull an average up.

    A crop chosen on the average then fails in every unremarkable year.
    """
    variable = [0.0] * 8 + [400.0, 500.0, 600.0]
    dependable = pixel(run("dependable-rainfall", stack_of("y", variable)))
    assert dependable == pytest.approx(0.0)
    assert dependable < float(np.mean(variable))


# 3. rainfall-variability


def test_rainfall_variability_is_the_spread_as_a_share_of_the_average():
    values = [80.0, 120.0] * 6  # mean 100, population deviation 20
    assert pixel(run("rainfall-variability", stack_of("y", values))) == pytest.approx(
        20.0
    )


def test_a_place_with_no_rain_reads_as_wholly_undependable_not_as_missing():
    """The Sahara divided by nothing.

    Masking it would leave the largest desert on earth transparent, and
    transparent over a light basemap reads as a low value. Rain that is absent
    is not rain whose reliability is unknown.
    """
    out = run("rainfall-variability", stack_of("y", [0.0] * 12))
    assert not np.ma.getmaskarray(out)[0]
    assert pixel(out) == pytest.approx(150.0)


def test_steady_rain_scores_far_below_the_marginal_line():
    steady = pixel(run("rainfall-variability", stack_of("y", [100.0] * 12)))
    erratic = pixel(
        run("rainfall-variability", stack_of("y", [0.0, 0.0, 300.0, 900.0] * 3))
    )
    assert steady == pytest.approx(0.0)
    assert erratic > 30.0  # the conventional line for marginal rainfed cropping


# 4. consecutive-dry-months


def dry_year(rain, demand):
    stack = stack_of("p", rain)
    stack.update(stack_of("e", demand))
    return stack


def test_consecutive_dry_months_takes_the_longest_run_not_the_count():
    # eight dry months in total, but the longest unbroken run is five
    rain = [0.0] * 5 + [100.0] * 4 + [0.0] * 3
    demand = [100.0] * 12
    assert pixel(run("consecutive-dry-months", dry_year(rain, demand))) == 5.0


def test_a_month_is_dry_below_half_of_what_the_air_can_evaporate():
    demand = [100.0] * 12
    assert pixel(run("consecutive-dry-months", dry_year([49.0] * 12, demand))) == 12.0
    assert pixel(run("consecutive-dry-months", dry_year([51.0] * 12, demand))) == 0.0


def test_a_frozen_month_is_not_counted_as_a_dry_one():
    """Siberia in winter: almost no rain, and almost no demand either.

    There is no moisture deficit in a month where the air can evaporate a
    tenth of a millimetre, and counting one would paint the whole Arctic as a
    twelve-month drought.
    """
    out = run("consecutive-dry-months", dry_year([2.0] * 12, [0.1] * 12))
    assert pixel(out) == 0.0


# 5. aridity-annual


def test_aridity_annual_sums_the_year_before_dividing():
    """Not the average of twelve monthly ratios, which is a different number.

    A Mediterranean winter runs far above demand and a summer has none; the
    monthly ratios average to something humid, while the year's totals say
    semi-arid, and semi-arid is what the place is.
    """
    rain = [200.0] * 3 + [0.0] * 9
    demand = [20.0] * 3 + [200.0] * 9
    out = run("aridity-annual", dry_year(rain, demand))
    assert pixel(out) == pytest.approx(600.0 / 1860.0)
    monthly_ratios = np.mean([200 / 20] * 3 + [0.0] * 9)
    assert pixel(out) < monthly_ratios


def test_aridity_annual_puts_a_desert_in_the_arid_class():
    out = run("aridity-annual", dry_year([2.0] * 12, [250.0] * 12))
    assert pixel(out) == pytest.approx(24.0 / 3000.0)
    assert pixel(out) < 0.05  # hyper-arid


def test_a_place_the_air_cannot_evaporate_from_is_answered_not_masked():
    out = run("aridity-annual", dry_year([1.0] * 12, [0.0] * 12))
    assert not np.ma.getmaskarray(out)[0]
    assert pixel(out) == pytest.approx(1.0)


# 6. fournier-erosivity


def test_fournier_rises_when_the_same_rain_arrives_in_fewer_months():
    even = pixel(run("fournier-erosivity", stack_of("p", [100.0] * 12)))
    concentrated = pixel(
        run("fournier-erosivity", stack_of("p", [400.0] * 3 + [0.0] * 9))
    )
    assert even == pytest.approx(100.0)
    assert concentrated == pytest.approx(400.0)
    assert concentrated > even  # same 1200 mm, four times the erosivity


def test_a_year_without_rain_is_zero_erosivity_rather_than_unknown():
    out = run("fournier-erosivity", stack_of("p", [0.0] * 12))
    assert not np.ma.getmaskarray(out)[0]
    assert pixel(out) == 0.0


# 7. gdd-shift


def warmth(tmax_c, tmin_c, tmax_then_c, tmin_then_c):
    return {
        "tmax": arr(tmax_c + KELVIN),
        "tmin": arr(tmin_c + KELVIN),
        "tmax_then": arr(tmax_then_c + KELVIN),
        "tmin_then": arr(tmin_then_c + KELVIN),
    }


def test_gdd_shift_is_the_difference_between_two_julys():
    # now: 24/16 -> mean 20 -> 10 above base, over 31 days
    # then: 22/14 -> mean 18 ->  8 above base, over 31 days
    out = run("gdd-shift", warmth(24.0, 16.0, 22.0, 14.0))
    assert pixel(out) == pytest.approx((10.0 - 8.0) * 31)


def test_gdd_shift_caps_the_afternoon_at_thirty():
    """Above 30 C maize gains no further development.

    Without the cap the hot lowlands would show the largest gains anywhere,
    which reads as land improving where the truth is the opposite.
    """
    already_hot = run("gdd-shift", warmth(40.0, 24.0, 34.0, 24.0))
    assert pixel(already_hot) == pytest.approx(0.0)
    still_below = run("gdd-shift", warmth(28.0, 24.0, 26.0, 24.0))
    assert pixel(still_below) > 0.0


def test_gdd_shift_uses_the_length_of_each_month():
    stack = warmth(24.0, 16.0, 22.0, 14.0)
    february = run("gdd-shift", stack, {"time": "2026-02-01"})
    # February 2026 has 28 days and February 2006 had 28 as well
    assert pixel(february) == pytest.approx(2.0 * 28)


def test_gdd_shift_reaches_back_in_months_not_days():
    R = ALL

    offsets = {i.role: i.offset_months for i in R["gdd-shift"].inputs}
    assert offsets["tmax_then"] == -240
    assert all(i.offset_days == 0 for i in R["gdd-shift"].inputs)


# 8. night-warming


def baseline(now_c, years_c):
    stack = {"tmin": arr(now_c + KELVIN)}
    for year, value in zip(range(1979, 1999), years_c):
        stack[f"b{year}"] = arr(value + KELVIN)
    return stack


def test_night_warming_subtracts_the_mean_of_the_baseline_years():
    out = run("night-warming", baseline(21.5, [20.0] * 10 + [21.0] * 10))
    assert pixel(out) == pytest.approx(21.5 - 20.5)


def test_night_warming_is_a_difference_so_kelvin_needs_no_conversion():
    out = run("night-warming", baseline(20.0, [20.0] * 20))
    assert pixel(out) == pytest.approx(0.0)


def test_the_night_warming_baseline_is_fixed_in_calendar_years():
    """A baseline that slides with the date being viewed is not a baseline."""
    R = ALL

    years = sorted(i.at_year for i in R["night-warming"].inputs if i.at_year)
    assert years == list(range(1979, 1999))
    assert R["night-warming"].inputs[0].at_year is None  # the month being asked about


# 10. months-since-rain


def test_months_since_rain_counts_back_to_the_last_wet_month():
    rain = [0.0, 0.0, 0.0, 40.0] + [0.0] * 20
    assert pixel(run("months-since-rain", stack_of("p", rain))) == 3.0


def test_it_rained_this_month_is_zero():
    assert pixel(run("months-since-rain", stack_of("p", [30.0] + [0.0] * 23))) == 0.0


def test_twenty_millimetres_is_the_bar_and_a_drizzle_does_not_clear_it():
    assert pixel(run("months-since-rain", stack_of("p", [19.0] + [30.0] * 23)) ) == 1.0
    assert pixel(run("months-since-rain", stack_of("p", [21.0] + [0.0] * 23))) == 0.0


def test_a_place_that_never_rains_reads_as_the_whole_window():
    """The top of the scale means "at least", not "exactly".

    The hyper-arid cores of the Sahara and the Atacama have gone longer than
    this map can see, which is what the notes say.
    """
    out = run("months-since-rain", stack_of("p", [0.0] * 24))
    assert not np.ma.getmaskarray(out)[0]
    assert pixel(out) == 24.0


# 9. livestock-heat


def test_the_heat_index_is_worse_in_humid_air_than_in_dry_air():
    """35 C in a desert is easier on a cow than 30 C in a wet monsoon.

    A map of temperature alone says the opposite, which is the whole reason
    for combining the two.
    """
    dry = pixel(run("livestock-heat", {"tmax": arr(35 + KELVIN), "humidity": arr(10.0)}))
    humid = pixel(
        run("livestock-heat", {"tmax": arr(30 + KELVIN), "humidity": arr(85.0)})
    )
    assert humid > dry


def test_the_heat_index_matches_the_published_form():
    # T = 30 C, RH = 60: (1.8*30+32) - (0.55 - 0.0055*60) * (1.8*30 - 26)
    out = run("livestock-heat", {"tmax": arr(30 + KELVIN), "humidity": arr(60.0)})
    expected = 86.0 - (0.55 - 0.33) * 28.0
    assert pixel(out) == pytest.approx(expected)


def test_the_heat_index_lands_in_its_operational_classes():
    # The published classes. They cannot be imported: the file is named after
    # the id it declares, and no import statement accepts a hyphen.
    MILD, MODERATE, SEVERE = 72.0, 80.0, 90.0

    comfortable = pixel(
        run("livestock-heat", {"tmax": arr(18 + KELVIN), "humidity": arr(50.0)})
    )
    hard = pixel(
        run("livestock-heat", {"tmax": arr(38 + KELVIN), "humidity": arr(70.0)})
    )
    assert comfortable < MILD
    assert hard > SEVERE
    assert MILD < MODERATE < SEVERE
