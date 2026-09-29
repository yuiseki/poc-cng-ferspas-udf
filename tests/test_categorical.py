"""The third scale, and the classification that needed it."""

import numpy as np
import pytest

from ferspas_tile.analysis import (
    CATEGORICAL,
    DIVERGING,
    PALETTE,
    SEQUENTIAL,
    Analysis,
    Input,
)
from ferspas_tile.climate_axes import MEAN, STD
from ferspas_tile.climate_types import CENTRES, LABELS, classify
from ferspas_tile.functions import REGISTRY
from tests.test_climate_axes import average_month, pixel, stack_of


def a_classification(**kwargs):
    defaults = dict(
        id="test",
        title="Test",
        question="Which type is this?",
        explanation=" ".join(["word"] * 25),
        unit="type",
        inputs=(Input("AGERA5-PF-M", role="rain"),),
        compute=lambda stack, params: stack["rain"],
        rescale=(0.0, 2.0),
        scale=CATEGORICAL,
        classes=("a", "b", "c"),
    )
    defaults.update(kwargs)
    return Analysis(**defaults)


# -- the contract ----------------------------------------------------------


def test_a_classification_is_accepted():
    spec = a_classification()
    assert spec.colormap_name is None
    assert len(spec.palette()) == 3


def test_a_classification_needs_classes_to_name():
    with pytest.raises(ValueError, match="needs classes"):
        a_classification(classes=("only one",), rescale=(0.0, 1.0))


def test_a_classification_may_not_have_more_classes_than_colours():
    many = tuple(str(i) for i in range(len(PALETTE) + 1))
    with pytest.raises(ValueError, match="repeated colour"):
        a_classification(classes=many, rescale=(0.0, float(len(many) - 1)))


def test_a_classification_declares_the_range_of_its_class_numbers():
    # The renderer uses the output as an index, so a rescale that says anything
    # else is a lie that would only show up as wrong colours.
    with pytest.raises(ValueError, match="range of class numbers"):
        a_classification(rescale=(0.0, 10.0))


def test_a_classification_has_no_neutral():
    with pytest.raises(ValueError, match="no neutral"):
        a_classification(neutral=0.0)


def test_only_a_classification_may_list_classes():
    with pytest.raises(ValueError, match="only a categorical"):
        a_classification(scale=SEQUENTIAL, classes=("a", "b"), rescale=(0.0, 1.0))


def test_the_other_two_scales_still_have_no_classes_and_keep_their_ramps():
    for scale, extra in ((SEQUENTIAL, {}), (DIVERGING, {"neutral": 0.0})):
        spec = a_classification(
            scale=scale, classes=(), rescale=(-1.0, 1.0), **extra
        )
        assert spec.colormap_name in ("viridis", "rdbu")
        assert spec.palette() == ()


def test_the_palette_has_no_duplicate_colours():
    assert len(set(PALETTE)) == len(PALETTE)


def test_the_reading_names_every_class():
    reading = a_classification().reading()
    for name in ("a", "b", "c"):
        assert name in reading


def test_describe_carries_the_classes_and_their_colours():
    described = a_classification().describe()
    assert described["classes"] == ["a", "b", "c"]
    assert len(described["palette"]) == 3
    assert described["colormap"] is None


# -- the fitted centres ----------------------------------------------------


def test_there_is_one_label_for_every_centre():
    assert len(LABELS) == len(CENTRES)


def test_every_centre_has_a_value_for_every_variable():
    assert {len(c) for c in CENTRES} == {len(MEAN)}


def test_the_centres_are_listed_along_the_warmth_axis():
    # The order is the only ranking a categorical map carries, so it has to be
    # the one the fitting script claims to have sorted by.
    #
    # It is the warmth axis and not the temperature. Those disagree for the two
    # hot types: the dry one is the warmer by thermometer and the wet one is
    # higher on the axis, because the axis counts evaporative demand too. This
    # test asserts the axis because that is what the script sorts by; a version
    # of it written against temperature failed, which is how the difference
    # came to be written down here instead of being assumed away.
    from ferspas_tile.climate_axes import WARMTH_AXIS

    scores = [sum(c[i] * WARMTH_AXIS[i] for i in range(len(c))) for c in CENTRES]
    assert scores == sorted(scores)


def test_the_two_hot_types_are_separated_by_water_and_not_by_heat():
    # The reason a classification was worth adding: a sequential ramp would
    # have drawn these two as neighbouring shades.
    dry, wet = CENTRES[2], CENTRES[3]
    heat_gap = abs((dry[2] + dry[3]) / 2 - (wet[2] + wet[3]) / 2)
    water_gap = abs(dry[0] - wet[0])
    assert water_gap > 10 * heat_gap


def test_a_month_at_a_centre_is_classified_as_that_centre():
    for index, centre in enumerate(CENTRES):
        real = [centre[i] * STD[i] + MEAN[i] for i in range(len(MEAN))]
        stack = stack_of(real[0], real[1], real[2], real[3])
        assert pixel(classify(stack)) == index


def test_a_frozen_month_is_the_first_type_and_a_soaked_one_is_the_last():
    frozen = stack_of(2.0, 1.0, -40.0, -46.0)
    soaked = stack_of(600.0, 100.0, 27.0, 22.0)
    assert pixel(classify(frozen)) == 0
    assert pixel(classify(soaked)) == len(CENTRES) - 1


def test_classifying_keeps_the_mask():
    masked = average_month()
    masked["demand"] = np.ma.masked_array([50.0], mask=[True])
    assert np.ma.getmaskarray(classify(masked))[0]


# -- the analysis ----------------------------------------------------------


def test_climate_type_is_registered_as_a_classification():
    spec = REGISTRY["climate-type"]
    assert spec.scale == CATEGORICAL
    assert spec.classes == LABELS
    assert len(spec.inputs) == 4


def test_climate_type_only_ever_returns_a_class_number():
    spec = REGISTRY["climate-type"]
    for rain, demand, tmax, tmin in (
        (0.0, 0.0, -50.0, -60.0),
        (500.0, 200.0, 40.0, 30.0),
        (36.5, 41.9, -11.2, -17.5),
    ):
        out = spec.compute(stack_of(rain, demand, tmax, tmin), {})
        assert 0 <= pixel(out) <= len(spec.classes) - 1
        assert float(pixel(out)).is_integer()
