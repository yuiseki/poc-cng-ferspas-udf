"""The loader: one file per analysis, named after its id."""

import pytest

from ferspas_tile.functions import FUNCTIONS_DIR, REGISTRY, load_functions

FRAMEWORK = '''
from ferspas_tile.analysis import Analysis, Input, SEQUENTIAL

def compute(stack, params):
    return stack["value"]

ANALYSIS = Analysis(
    id={id!r},
    title="t",
    question="?",
    explanation=(
        "A placeholder explanation that is long enough to satisfy the rule that"
        " every analysis has to say what it is for in plain words."
    ),
    unit="x",
    inputs=(Input("A"),),
    compute=compute,
    rescale=(0.0, 1.0),
    scale=SEQUENTIAL,
)
'''


def test_every_file_in_the_package_is_registered():
    on_disk = {
        path.stem for path in FUNCTIONS_DIR.glob("*.py") if not path.name.startswith("_")
    }
    assert on_disk == set(REGISTRY)


def test_a_hyphenated_id_still_loads():
    # No import statement accepts these names; they load from their path.
    assert "water-balance" in REGISTRY
    assert "diurnal-range" in REGISTRY


def test_the_id_and_the_filename_must_match(tmp_path):
    (tmp_path / "expected-id.py").write_text(FRAMEWORK.format(id="something-else"))
    with pytest.raises(ValueError, match="file name and the id"):
        load_functions(tmp_path)


def test_a_file_without_an_analysis_is_an_error_not_a_skip(tmp_path):
    (tmp_path / "empty.py").write_text("X = 1\n")
    with pytest.raises(TypeError, match="does not define an ANALYSIS"):
        load_functions(tmp_path)


def test_a_broken_file_raises_rather_than_vanishing(tmp_path):
    (tmp_path / "broken.py").write_text("def (:\n")
    with pytest.raises(SyntaxError):
        load_functions(tmp_path)


def test_underscore_files_are_not_analyses(tmp_path):
    (tmp_path / "__init__.py").write_text("")
    (tmp_path / "_helper.py").write_text("X = 1\n")
    (tmp_path / "ok.py").write_text(FRAMEWORK.format(id="ok"))
    assert set(load_functions(tmp_path)) == {"ok"}


def test_files_load_in_name_order(tmp_path):
    for name in ("zebra", "apple", "mango"):
        (tmp_path / f"{name}.py").write_text(FRAMEWORK.format(id=name))
    assert list(load_functions(tmp_path)) == ["apple", "mango", "zebra"]


def test_an_analysis_that_breaks_the_colour_contract_fails_at_load(tmp_path):
    broken = FRAMEWORK.replace("SEQUENTIAL", "DIVERGING").replace(
        "rescale=(0.0, 1.0)", "rescale=(-1.0, 10.0),\n    neutral=0.0"
    )
    (tmp_path / "skewed.py").write_text(broken.format(id="skewed"))
    with pytest.raises(ValueError, match="not symmetric"):
        load_functions(tmp_path)
