"""Each detection route in isolation, absence as a normal outcome, and an
unsupported release reported distinctly from no AEDT at all -- see
`.superpowers/sdd/m10-task-2-brief.md`.
"""

from __future__ import annotations

import platform
from pathlib import Path

import pytest

from inductor_designer.adapters.system import installations
from inductor_designer.application.services.aedt_support import SUPPORTED_AEDT_RELEASE
from inductor_designer.domain.aedt_target import AedtRelease


class _FakeKey:
    """A registry key handle: just the full backslash-joined path opened to
    reach it, so `_FakeWinreg` can look itself back up by that path."""

    def __init__(self, path: str) -> None:
        self.path = path

    def __enter__(self) -> _FakeKey:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


class _FakeWinreg:
    """A `winreg` stand-in shaped exactly like the real on-machine registry
    this module reads: one version subkey, `2025.2`, under
    `SOFTWARE\\Ansoft\\ElectronicsDesktop`, holding a `Desktop` subkey with
    an `InstallationDirectory` value. Used in place of `_import_winreg()`,
    never in place of `_registry_entries()` itself -- so the real key path,
    the `Desktop` level, and the value name are all actually exercised.
    """

    HKEY_LOCAL_MACHINE = object()

    # Hard-coded to the real on-machine string, deliberately NOT read back
    # from `installations._REGISTRY_KEY`: reading it back would make this
    # fake agree with whatever that constant says, correct or not, and the
    # whole point of this test is to catch the constant being wrong.
    _SUBKEYS = {r"SOFTWARE\Ansoft\ElectronicsDesktop": ["2025.2"]}
    _VALUES = {
        r"SOFTWARE\Ansoft\ElectronicsDesktop\2025.2\Desktop": {
            "InstallationDirectory": r"C:\Program Files\ANSYS Inc\v252\AnsysEM",
        }
    }

    def OpenKey(self, hive_or_key: object, subpath: str) -> _FakeKey:  # noqa: N802
        base = "" if hive_or_key is self.HKEY_LOCAL_MACHINE else hive_or_key.path  # type: ignore[union-attr]
        path = f"{base}\\{subpath}" if base else subpath
        if path not in self._SUBKEYS and path not in self._VALUES:
            raise OSError(f"fake registry: key does not exist: {path}")
        return _FakeKey(path)

    def EnumKey(self, key: _FakeKey, index: int) -> str:  # noqa: N802
        names = self._SUBKEYS.get(key.path, [])
        if index >= len(names):
            raise OSError("fake registry: no more subkeys")
        return names[index]

    def QueryValueEx(self, key: _FakeKey, name: str) -> tuple[str, int]:  # noqa: N802
        values = self._VALUES.get(key.path, {})
        if name not in values:
            raise OSError(f"fake registry: value does not exist: {name}")
        return values[name], 1


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
        installations, "_registry_entries", lambda: iter([("2025.2", str(install_root))])
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
        lambda: iter([("2025.2", str(tmp_path / "gone"))]),
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
        installations, "_registry_entries", lambda: iter([("2024.2", str(install_root))])
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
        lambda: iter([("2024.2", str(old_root)), ("2025.2", str(new_root))]),
    )

    found = installations.detect_aedt()

    assert found is not None
    assert found.release == SUPPORTED_AEDT_RELEASE
    assert found.install_root == new_root
    assert installations.detect_unsupported_aedt() is None


def test_the_newest_unsupported_release_wins_when_several_are_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Decision (minor finding 4): a workstation upgraded from one release to
    a newer one keeps both registry entries; which one wins is deliberate,
    not accidental -- the newest, since that is the one actually worth
    naming in the "you have the wrong release" message. Uses 2024 R2 and
    2025 R1 (not, say, 2024 R1) because `AedtRelease` itself refuses
    anything older than 2024 R2 -- see `domain/aedt_target.py`."""
    _clear_all_routes(monkeypatch)
    older_root = tmp_path / "v242-install"
    older_root.mkdir()
    newer_root = tmp_path / "v251-install"
    newer_root.mkdir()
    monkeypatch.setattr(
        installations,
        "_registry_entries",
        lambda: iter([("2024.2", str(older_root)), ("2025.1", str(newer_root))]),
    )

    unsupported = installations.detect_unsupported_aedt()

    assert unsupported is not None
    assert unsupported.release == AedtRelease(2025, 1)
    assert unsupported.install_root == newer_root


def test_registry_entries_reads_the_real_on_machine_key_layout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pins the real registry layout this route depends on -- confirmed with
    `reg query` against a real AEDT 2025 R2 install: the version subkey lives
    under `SOFTWARE\\Ansoft\\ElectronicsDesktop` (not `Ansys Inc\\AnsysEM`),
    the install path is one level below that, in a `Desktop` subkey, under
    the name `InstallationDirectory` (not `InstallDir`), and the version
    subkey itself is shaped "2025.2" (not "252"). Exercises the real
    `_registry_entries()`, not a faked seam -- the whole point being that a
    faked seam is exactly what let all four of these be wrong at once and
    still have every test pass.
    """
    monkeypatch.setattr(installations, "_import_winreg", lambda: _FakeWinreg())

    assert list(installations._registry_entries()) == [
        ("2025.2", r"C:\Program Files\ANSYS Inc\v252\AnsysEM")
    ]


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
    assert found is not None
    assert found.install_root.is_absolute()


@pytest.mark.skipif(
    platform.system() != "Windows",
    reason="drive-letter paths are absolute only on Windows",
)
def test_drive_root_of_a_bare_drive_letter_is_the_absolute_drive_root() -> None:
    """The actual bug (Important 2): `SYSTEMDRIVE` holds a bare "C:", and
    `Path("C:") / "x"` is relative to the current directory, not the drive
    root -- only `Path("C:/") / "x"` (or `"C:\\\\"`) is absolute. The
    `tmp_path`-based test above can't catch this: `str(tmp_path)` is already
    a multi-segment absolute path, so the buggy and fixed joins agree by
    coincidence. This test exercises the join directly, on a bare
    drive-letter-shaped input, with no real filesystem or cwd involved.
    """
    root = installations._drive_root("C:")

    assert root.is_absolute()
    assert root == Path("C:/")
