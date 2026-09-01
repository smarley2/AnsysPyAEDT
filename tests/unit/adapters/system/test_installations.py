"""Each detection route in isolation, absence as a normal outcome, and an
unsupported release reported distinctly from no AEDT at all -- see
`.superpowers/sdd/m10-task-2-brief.md`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from inductor_designer.adapters.system import installations
from inductor_designer.application.services.aedt_support import SUPPORTED_AEDT_RELEASE
from inductor_designer.domain.aedt_target import AedtRelease


def _clear_all_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    """No route answers unless a test deliberately arms one."""
    monkeypatch.delenv(installations._ENV_VARIABLE, raising=False)
    monkeypatch.delenv("PROGRAMFILES", raising=False)
    monkeypatch.delenv("SYSTEMDRIVE", raising=False)
    monkeypatch.setattr(installations, "_registry_entries", lambda: iter(()))


# ---------------------------------------------------------------------------
# AEDT absent
# ---------------------------------------------------------------------------


def test_aedt_absent_reports_none_from_every_function(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_all_routes(monkeypatch)

    assert installations.detect_aedt() is None
    assert installations.detect_unsupported_aedt() is None


# ---------------------------------------------------------------------------
# Route 1: environment variable
# ---------------------------------------------------------------------------


def test_environment_variable_route_finds_the_supported_release(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _clear_all_routes(monkeypatch)
    install_root = tmp_path / "ANSYSEM_from_env"
    install_root.mkdir()
    monkeypatch.setenv(installations._ENV_VARIABLE, str(install_root))

    found = installations.detect_aedt()

    assert found == installations.AedtInstallation(
        SUPPORTED_AEDT_RELEASE, install_root, installations.DetectionRoute.ENVIRONMENT_VARIABLE
    )
    assert installations.detect_unsupported_aedt() is None


def test_environment_variable_pointing_nowhere_is_not_trusted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A stale variable left behind by an uninstalled version must not be
    reported as a live installation."""
    _clear_all_routes(monkeypatch)
    monkeypatch.setenv(installations._ENV_VARIABLE, str(tmp_path / "does-not-exist"))

    assert installations.detect_aedt() is None


# ---------------------------------------------------------------------------
# Route 2: standard location
# ---------------------------------------------------------------------------


def test_standard_location_route_finds_the_supported_release(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _clear_all_routes(monkeypatch)
    program_files = tmp_path / "Program Files"
    install_root = program_files / "ANSYS Inc" / installations._STANDARD_VERSION_DIRNAME / "AnsysEM"
    install_root.mkdir(parents=True)
    monkeypatch.setenv("PROGRAMFILES", str(program_files))

    found = installations.detect_aedt()

    assert found == installations.AedtInstallation(
        SUPPORTED_AEDT_RELEASE, install_root, installations.DetectionRoute.STANDARD_LOCATION
    )


def test_environment_variable_route_is_tried_before_standard_location(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _clear_all_routes(monkeypatch)
    env_root = tmp_path / "from-env"
    env_root.mkdir()
    program_files = tmp_path / "Program Files"
    standard_root = (
        program_files / "ANSYS Inc" / installations._STANDARD_VERSION_DIRNAME / "AnsysEM"
    )
    standard_root.mkdir(parents=True)
    monkeypatch.setenv(installations._ENV_VARIABLE, str(env_root))
    monkeypatch.setenv("PROGRAMFILES", str(program_files))

    found = installations.detect_aedt()

    assert found is not None
    assert found.route is installations.DetectionRoute.ENVIRONMENT_VARIABLE
    assert found.install_root == env_root


# ---------------------------------------------------------------------------
# Route 3: registry
# ---------------------------------------------------------------------------


def test_registry_route_finds_the_supported_release_when_the_first_two_miss(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _clear_all_routes(monkeypatch)
    install_root = tmp_path / "from-registry"
    install_root.mkdir()
    monkeypatch.setattr(
        installations, "_registry_entries", lambda: iter([("252", str(install_root))])
    )

    found = installations.detect_aedt()

    assert found == installations.AedtInstallation(
        SUPPORTED_AEDT_RELEASE, install_root, installations.DetectionRoute.REGISTRY
    )


def test_registry_route_ignores_an_install_dir_that_does_not_exist(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _clear_all_routes(monkeypatch)
    monkeypatch.setattr(
        installations,
        "_registry_entries",
        lambda: iter([("252", str(tmp_path / "gone"))]),
    )

    assert installations.detect_aedt() is None


def test_registry_route_ignores_a_token_it_cannot_parse(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _clear_all_routes(monkeypatch)
    install_root = tmp_path / "weird-token"
    install_root.mkdir()
    monkeypatch.setattr(
        installations, "_registry_entries", lambda: iter([("not-a-token", str(install_root))])
    )

    assert installations.detect_aedt() is None
    assert installations.detect_unsupported_aedt() is None


def _raising_registry_entries() -> object:
    raise OSError("registry access denied")


def test_a_registry_that_raises_is_absence_not_a_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_all_routes(monkeypatch)
    monkeypatch.setattr(installations, "_registry_entries", _raising_registry_entries)

    assert installations.detect_aedt() is None
    assert installations.detect_unsupported_aedt() is None


def test_winreg_unavailable_is_absence_not_an_import_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulates the Linux CI runner, where `winreg` does not exist at all --
    without depending on which real platform this test happens to run on.
    Exercises the real `_registry_entries`, not a fake of it."""
    monkeypatch.delenv(installations._ENV_VARIABLE, raising=False)
    monkeypatch.delenv("PROGRAMFILES", raising=False)
    monkeypatch.setattr(installations, "_import_winreg", lambda: None)

    assert list(installations._registry_entries()) == []
    assert installations.detect_aedt() is None


# ---------------------------------------------------------------------------
# An unsupported release is not the same as absence
# ---------------------------------------------------------------------------


def test_an_unsupported_release_is_reported_distinctly_from_absence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A v242-only machine: `detect_aedt()` must say "not found" only in the
    "nothing is here" sense would be wrong -- it must say nothing SUPPORTED
    is here, while `detect_unsupported_aedt()` names what actually is."""
    _clear_all_routes(monkeypatch)
    install_root = tmp_path / "v242-install"
    install_root.mkdir()
    monkeypatch.setattr(
        installations, "_registry_entries", lambda: iter([("242", str(install_root))])
    )

    assert installations.detect_aedt() is None
    unsupported = installations.detect_unsupported_aedt()
    assert unsupported == installations.UnsupportedAedtInstallation(
        AedtRelease(2024, 2), install_root, installations.DetectionRoute.REGISTRY
    )


def test_the_supported_release_among_others_wins_over_an_unsupported_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _clear_all_routes(monkeypatch)
    old_root = tmp_path / "v242-install"
    old_root.mkdir()
    new_root = tmp_path / "v252-install"
    new_root.mkdir()
    monkeypatch.setattr(
        installations,
        "_registry_entries",
        lambda: iter([("242", str(old_root)), ("252", str(new_root))]),
    )

    found = installations.detect_aedt()

    assert found is not None
    assert found.release == SUPPORTED_AEDT_RELEASE
    assert found.install_root == new_root
    assert installations.detect_unsupported_aedt() is None


# ---------------------------------------------------------------------------
# FEMM: absent is normal, present is reported
# ---------------------------------------------------------------------------


def test_femm_absent_is_none_not_a_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_all_routes(monkeypatch)

    assert installations.detect_femm() is None


def test_femm_absent_without_a_system_drive_variable_is_still_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Linux CI runner has no `SYSTEMDRIVE` at all."""
    monkeypatch.delenv("SYSTEMDRIVE", raising=False)

    assert installations.detect_femm() is None


def test_femm_found_at_its_standard_location(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    femm_root = tmp_path / "femm42"
    (femm_root / "bin").mkdir(parents=True)
    (femm_root / "bin" / "femm.exe").write_bytes(b"")
    monkeypatch.setenv("SYSTEMDRIVE", str(tmp_path))

    found = installations.detect_femm()

    assert found == installations.FemmInstallation(
        femm_root, installations.DetectionRoute.STANDARD_LOCATION
    )
