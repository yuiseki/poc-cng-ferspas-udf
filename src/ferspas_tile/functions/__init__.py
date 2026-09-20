"""The analyses, one file per id.

`water-balance.py` defines the analysis whose id is `water-balance`. A file is
picked up by being here: nothing registers it by hand, and a mismatch between
the filename and the id it declares is an error rather than a file that loads
under a name nobody expects.

Ids contain hyphens, which no Python import statement will accept, so each file
is loaded from its path. That is the price of "the filename is the id", and it
is worth paying: a reader looking for `water-balance` finds `water-balance.py`.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from ..analysis import Analysis

FUNCTIONS_DIR = Path(__file__).resolve().parent

REGISTRY: dict[str, Analysis] = {}


def _load_one(path: Path) -> Analysis:
    name = f"{__name__}.{path.stem.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load analysis from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    analysis = getattr(module, "ANALYSIS", None)
    if not isinstance(analysis, Analysis):
        raise TypeError(f"{path.name} does not define an ANALYSIS")
    if analysis.id != path.stem:
        raise ValueError(
            f"{path.name} declares id {analysis.id!r};"
            f" the file name and the id have to match"
        )
    return analysis


def load_functions(directory: Path | None = None) -> dict[str, Analysis]:
    """Read every analysis file in a directory, in name order."""
    directory = directory or FUNCTIONS_DIR
    found: dict[str, Analysis] = {}
    for path in sorted(directory.glob("*.py")):
        if path.name.startswith("_"):
            continue
        analysis = _load_one(path)
        if analysis.id in found:
            raise ValueError(f"two files declare the id {analysis.id!r}")
        found[analysis.id] = analysis
    return found


# Loaded at import: a broken analysis file should stop the server rather than
# disappear from the registry and look like it was never written.
REGISTRY.update(load_functions())
