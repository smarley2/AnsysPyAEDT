from pathlib import Path


def test_runner_fixes_material_and_supported_solver_environment() -> None:
    script = Path("tools/run_m5a_material_validation.ps1").read_text(encoding="utf-8")
    for expected in (
        "'2025.2'",
        "'commercial'",
        "'Magnetics'",
        "'High Flux'",
        "'60'",
        "'C058071A2'",
        "'bh-25c'",
        "INDUCTOR_M5A_PROJECT",
        "INDUCTOR_M5A_ARTIFACT_ROOT",
        "INDUCTOR_FEMM_LIVE",
    ):
        assert expected in script
    assert "git add" not in script
    assert "git commit" not in script
