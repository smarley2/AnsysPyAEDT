import re
from pathlib import Path

import pytest


def release_validation_pattern() -> str:
    script = Path("tools/run_aedt_spike.ps1").read_text(encoding="utf-8")
    match = re.search(
        r"\[ValidatePattern\('([^']+)'\)\]\s*\[string\]\$Release",
        script,
    )
    assert match is not None
    return match.group(1)


@pytest.mark.parametrize("release", ["2024.2", "2025.1", "2099.2"])
def test_runner_release_validation_accepts_supported_boundaries(release: str) -> None:
    assert re.fullmatch(release_validation_pattern(), release)


@pytest.mark.parametrize("release", ["2024.1", "2023.2", "2100.1"])
def test_runner_release_validation_rejects_unsupported_boundaries(release: str) -> None:
    assert re.fullmatch(release_validation_pattern(), release) is None
