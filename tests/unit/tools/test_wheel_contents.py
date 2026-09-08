"""The wheel must carry the data the application reads, and not the build output.

Nothing asserted this before: deleting a `force-include` entry dropped an entire
resource directory from the wheel while every test stayed green, so a release
could ship an application that starts and then finds no schemas.
"""

from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

# Shipped because they are source, read at runtime, and absent from the default
# package selection. The catalog INDEX is deliberately not here: it is build
# output, `artifacts/` is git-ignored, and force-including it broke
# `pip install -e .` on every checkout that had not built it yet.
_SHIPPED = ("/schemas/", "/compatibility/", "/materials-overlay/")


@pytest.fixture(scope="module")
def built_wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output = tmp_path_factory.mktemp("wheel")
    result = subprocess.run(  # noqa: S603 - the interpreter running these tests
        [sys.executable, "-m", "hatchling", "build", "-t", "wheel", "-d", str(output)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip(f"hatchling is unavailable or failed: {result.stderr[-400:]}")
    wheels = sorted(output.glob("*.whl"))
    assert wheels, "hatchling reported success but produced no wheel"
    return wheels[-1]


def test_the_wheel_ships_every_runtime_resource(built_wheel: Path) -> None:
    with zipfile.ZipFile(built_wheel) as archive:
        names = archive.namelist()

    resources = [name for name in names if "_resources" in name]
    assert resources, "the wheel carries no shipped resources at all"
    for expected in _SHIPPED:
        assert any(expected in name for name in resources), (
            f"{expected} is missing from the wheel; a force-include entry was dropped"
        )


def test_the_wheel_does_not_ship_the_generated_catalog(built_wheel: Path) -> None:
    """Build output, not source.

    Shipping it would also mean an editable install could not be performed on a
    fresh clone, because a `force-include` entry is evaluated for the editable
    wheel too and the file does not exist until `tools.build_catalog` has run --
    which imports dependencies that arrive through that very install.
    """
    with zipfile.ZipFile(built_wheel) as archive:
        assert not [n for n in archive.namelist() if n.endswith("catalog.sqlite")]
