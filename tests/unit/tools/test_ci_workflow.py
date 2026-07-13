from pathlib import Path

import yaml


def test_linux_egl_runtime_is_installed_before_test_suite() -> None:
    workflow = yaml.safe_load(
        Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["test"]["steps"]

    egl_steps = [step for step in steps if "libegl1" in step.get("run", "")]
    assert len(egl_steps) == 1

    egl_step = egl_steps[0]
    assert egl_step.get("if") == "runner.os == 'Linux'"
    assert "sudo apt-get update" in egl_step["run"]
    assert "sudo apt-get install --yes libegl1" in egl_step["run"]

    test_step = next(step for step in steps if "python -m pytest" in step.get("run", ""))
    assert steps.index(egl_step) < steps.index(test_step)
