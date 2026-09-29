"""The fitted scale, and the three analyses built on it.

These check the properties the numbers have to have, not the numbers
themselves. A refitted constant should not break a test; a constant that has
stopped meaning what its name says should.
"""

import numpy as np
import pytest

from ferspas_tile.analysis import KELVIN
from ferspas_tile.climate_axes import (
    MEAN,
    STD,
    VARIABLES,
    WARMTH_AXIS,
    WATER_AXIS,
    mahalanobis_squared,
    project,
    standardise,
)
from ferspas_tile.functions import REGISTRY


def stack_of(rain, demand, tmax_c, tmin_c):
    def arr(value):
        return np.ma.masked_array(np.array([value], dtype="float64"))

    return {
        "rain": arr(rain),
        "demand": arr(demand),
        "tmax": arr(tmax_c + KELVIN),
        "tmin": arr(tmin_c + KELVIN),
    }


def average_month():
    """The month the fit calls average, in the units an analysis receives."""
    return stack_of(MEAN[0], MEAN[1], MEAN[2], MEAN[3])


def pixel(out):
    return float(np.ma.getdata(out)[0])


# -- the fitted constants --------------------------------------------------


def test_the_constants_line_up_with_the_variables():
    assert len(MEAN) == len(STD) == len(VARIABLES)
    assert len(WARMTH_AXIS) == len(WATER_AXIS) == len(VARIABLES)


def test_the_axes_are_unit_vectors_and_orthogonal():
    warmth, water = np.array(WARMTH_AXIS), np.array(WATER_AXIS)
    assert np.linalg.norm(warmth) == pytest.approx(1.0, abs=1e-5)
    assert np.linalg.norm(water) == pytest.approx(1.0, abs=1e-5)
    # Principal components are orthogonal by construction. If this fails the
    # constants were edited by hand rather than refitted.
    assert warmth @ water == pytest.approx(0.0, abs=1e-5)


def test_the_axes_point_the_way_their_names_say():
    # Sign is chosen in the fitting script, and the whole colour rule depends
    # on it: up the water axis has to mean more water.
    assert WARMTH_AXIS[VARIABLES.index("tmax")] > 0
    assert WARMTH_AXIS[VARIABLES.index("tmin")] > 0
    assert WATER_AXIS[VARIABLES.index("rain")] > 0


def test_the_water_axis_is_mostly_rain_and_the_warmth_axis_is_not():
    assert abs(WATER_AXIS[VARIABLES.index("rain")]) > 0.8
    assert abs(WARMTH_AXIS[VARIABLES.index("rain")]) < 0.5


# -- standardising ---------------------------------------------------------


def test_the_average_month_standardises_to_zero():
    for score in standardise(average_month()):
        assert pixel(score) == pytest.approx(0.0, abs=1e-9)


def test_one_spread_above_the_mean_standardises_to_one():
    one_up = stack_of(
        MEAN[0] + STD[0], MEAN[1] + STD[1], MEAN[2] + STD[2], MEAN[3] + STD[3]
    )
    for score in standardise(one_up):
        assert pixel(score) == pytest.approx(1.0, abs=1e-9)


def test_temperature_arrives_in_kelvin_and_is_scored_in_celsius():
    # The conversion lives in standardise(); an analysis that forgot it would
    # be 273 standard deviations from anywhere.
    scores = standardise(stack_of(MEAN[0], MEAN[1], MEAN[2], MEAN[3]))
    assert abs(pixel(scores[2])) < 1.0


# -- the axes --------------------------------------------------------------


def test_the_average_month_sits_at_zero_on_both_axes():
    assert pixel(project(average_month(), WARMTH_AXIS)) == pytest.approx(0.0, abs=1e-9)
    assert pixel(project(average_month(), WATER_AXIS)) == pytest.approx(0.0, abs=1e-9)


def test_a_warmer_month_moves_up_the_warmth_axis():
    warm = stack_of(MEAN[0], MEAN[1], MEAN[2] + 10, MEAN[3] + 10)
    cold = stack_of(MEAN[0], MEAN[1], MEAN[2] - 10, MEAN[3] - 10)
    assert pixel(project(warm, WARMTH_AXIS)) > 0 > pixel(project(cold, WARMTH_AXIS))


def test_a_wetter_month_moves_up_the_water_axis():
    wet = stack_of(MEAN[0] + 200, MEAN[1], MEAN[2], MEAN[3])
    dry = stack_of(0.0, MEAN[1], MEAN[2], MEAN[3])
    assert pixel(project(wet, WATER_AXIS)) > 0 > pixel(project(dry, WATER_AXIS))


def test_rain_barely_moves_the_warmth_axis_compared_with_the_water_axis():
    # The point of having two axes: at one temperature, rain still separates
    # places. If this stops holding, the second axis is not the wet-dry one.
    rain_only = stack_of(MEAN[0] + 100, MEAN[1], MEAN[2], MEAN[3])
    assert abs(pixel(project(rain_only, WATER_AXIS))) > 2 * abs(
        pixel(project(rain_only, WARMTH_AXIS))
    )


# -- the distance ----------------------------------------------------------


def test_the_average_month_is_at_no_distance():
    assert pixel(mahalanobis_squared(average_month())) == pytest.approx(0.0, abs=1e-9)


def test_distance_is_never_negative():
    for offsets in ((300, 0, 0, 0), (0, 300, 0, 0), (0, 0, 40, -40), (-30, -30, 30, 0)):
        out = mahalanobis_squared(
            stack_of(
                MEAN[0] + offsets[0],
                MEAN[1] + offsets[1],
                MEAN[2] + offsets[2],
                MEAN[3] + offsets[3],
            )
        )
        assert pixel(out) >= 0.0


def test_an_impossible_combination_is_further_than_a_large_ordinary_one():
    # Day and night temperatures move together almost everywhere, so pulling
    # them apart is stranger than moving both a long way together, even though
    # the second is the bigger change in millimetres and degrees.
    together = stack_of(MEAN[0], MEAN[1], MEAN[2] + 20, MEAN[3] + 20)
    apart = stack_of(MEAN[0], MEAN[1], MEAN[2] + 10, MEAN[3] - 10)
    assert pixel(mahalanobis_squared(apart)) > pixel(mahalanobis_squared(together))


def test_the_distance_keeps_the_mask():
    masked = average_month()
    masked["rain"] = np.ma.masked_array([100.0], mask=[True])
    assert np.ma.getmaskarray(mahalanobis_squared(masked))[0]


# -- the three analyses ----------------------------------------------------

AXES_ANALYSES = ("warmth-axis", "water-axis", "unusual-combination")


def test_all_three_are_registered_and_read_the_same_four_collections():
    for analysis_id in AXES_ANALYSES:
        spec = REGISTRY[analysis_id]
        assert [i.role for i in spec.inputs] == list(VARIABLES)
        assert len(spec.inputs) == 4, "four frames is the whole budget"
        assert all(i.offset_days == 0 and i.offset_months == 0 for i in spec.inputs)


def test_the_water_axis_keeps_the_rule_that_blue_is_more_water():
    spec = REGISTRY["water-axis"]
    assert spec.scale == "diverging"
    assert spec.neutral == 0.0
    wet = spec.compute(stack_of(MEAN[0] + 200, MEAN[1], MEAN[2], MEAN[3]), {})
    assert pixel(wet) > spec.neutral


def test_the_unusual_combination_map_is_zero_at_the_average_month():
    out = REGISTRY["unusual-combination"].compute(average_month(), {})
    assert pixel(out) == pytest.approx(0.0, abs=1e-9)
