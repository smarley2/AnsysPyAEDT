from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "filename",
    [
        "run_aedt_spike.ps1",
        "run_aedt_maxwell2d.ps1",
        "run_aedt_maxwell3d.ps1",
    ],
)
def test_controlled_runner_accepts_only_2025_r2_commercial(filename: str) -> None:
    script = (Path("tools") / filename).read_text(encoding="utf-8")
    assert "[ValidateSet('2025.2')]" in script
    assert "[ValidateSet('commercial')]" in script
    assert "student" not in script.casefold()
    assert "2024\\.2" not in script
