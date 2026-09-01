"""What AEDT and FEMM this machine actually has, discovered without starting
either.

Two products are optional and never assumed: FEMM 4.2 (`detect_femm`) is
genuinely optional, and its absence is a normal outcome, never a fault. AEDT
(`detect_aedt`) is the one this application drives, but this module answers
only "is the supported release installed", not "does it work" -- starting a
desktop to find out would spend a licence seat just to draw a label on a
screen nobody has asked to generate anything from yet, and the M8 solve path
already answers "does it work" for the run that actually needs to know. This
module never imports PyAEDT, `ansys.aedt.core`, or `femm`.

Cheapest first, for AEDT: the `ANSYSEM_ROOT<nnn>` environment variable AEDT
itself sets when it runs (an environment read); the standard install
location under `%PROGRAMFILES%\\ANSYS Inc\\v<nnn>\\AnsysEM` (one directory
check); the registry, last, because Ansys does not publish its layout, so
`_registry_entries()` is a best-effort fallback -- deliberately isolated
behind one seam so a test replaces it outright, never touching `winreg`.
`winreg` itself is imported lazily, inside that seam (`_import_winreg`),
because the non-solver suite runs on a Linux CI runner where the module does
not exist; importing it at module level would break every import of this
file there.

A release token is "<two-digit year><one-digit release>", e.g. "252" for
2025 R2 -- the exact scheme `ANSYSEM_ROOT252` and `v252` both use, so it is
derived once from `SUPPORTED_AEDT_RELEASE` rather than written as a literal
in three places.

An unsupported release found (say, only 2024 R2 is on the machine) is not the
same finding as no AEDT at all -- the remedies differ completely ("install
AEDT" versus "you have the wrong release") -- so `detect_unsupported_aedt()`
reports it as its own outcome rather than folding it into `detect_aedt()`'s
`None`.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from enum import Enum
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

from inductor_designer.application.services.aedt_support import SUPPORTED_AEDT_RELEASE
from inductor_designer.domain.aedt_target import AedtRelease

# "252" for 2025 R2 -- the token `ANSYSEM_ROOT<token>` and `v<token>` both use.
_RELEASE_TOKEN = f"{SUPPORTED_AEDT_RELEASE.year % 100:02d}{SUPPORTED_AEDT_RELEASE.release}"
_ENV_VARIABLE = f"ANSYSEM_ROOT{_RELEASE_TOKEN}"
_STANDARD_VERSION_DIRNAME = f"v{_RELEASE_TOKEN}"

# Best-effort fallback layout: Ansys does not publish this key, so it is
# reached only when the two cheaper routes both miss, and only ever through
# the `_registry_entries()` seam below.
_REGISTRY_KEY = r"SOFTWARE\Ansys Inc\AnsysEM"

# FEMM 4.2's documented default install location (femm.info); pyfemm expects
# it there, and FEMM sets no environment variable of its own the way AEDT
# does. `SYSTEMDRIVE` (normally "C:") is read rather than hard-coded so a
# test can redirect it under `tmp_path` -- the same trick the AEDT route
# plays with `PROGRAMFILES`.
_FEMM_RELATIVE_EXECUTABLE = Path("femm42") / "bin" / "femm.exe"


class DetectionRoute(str, Enum):
    """How a route succeeded -- the first thing worth knowing when a user
    reports "it says AEDT is missing"."""

    ENVIRONMENT_VARIABLE = "environment_variable"
    STANDARD_LOCATION = "standard_location"
    REGISTRY = "registry"


class AedtInstallation(NamedTuple):
    """The supported AEDT release, found. `install_root` is an absolute path
    -- see `app_logging.RedactingFormatter` before printing or logging it."""

    release: AedtRelease
    install_root: Path
    route: DetectionRoute


class UnsupportedAedtInstallation(NamedTuple):
    """An AEDT release present on this machine, but not the one this
    application supports. Reported separately from absence: "install AEDT"
    and "you have the wrong release" are different remedies."""

    release: AedtRelease
    install_root: Path
    route: DetectionRoute


class FemmInstallation(NamedTuple):
    """FEMM 4.2, found. Its absence is normal and is never reported as this
    type at all -- see `detect_femm()`."""

    install_root: Path
    route: DetectionRoute


def _is_directory(path: Path) -> bool:
    try:
        return path.is_dir()
    except OSError:
        return False


def _release_from_token(token: str) -> AedtRelease | None:
    """Parses "252" as 2025 R2; `None` for anything that is not a release
    token, or that `AedtRelease` itself refuses (older than 2024 R2)."""
    if len(token) != 3 or not token.isdigit():
        return None
    try:
        return AedtRelease(2000 + int(token[:2]), int(token[2]))
    except ValueError:
        return None


def _import_winreg() -> ModuleType | None:
    """`winreg` does not exist off Windows; isolated here so a test can force
    the "unavailable" path without depending on which platform it runs on."""
    try:
        import winreg
    except ImportError:
        return None
    return winreg


def _registry_entries() -> Iterator[tuple[str, str]]:
    """Yields (release token, install directory) for every AEDT entry the
    registry lists. Isolated in its own function so a test can replace it
    outright -- the one seam this module needs to be fully testable with no
    registry at all, on any platform.
    """
    winreg = _import_winreg()
    if winreg is None:
        return
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _REGISTRY_KEY) as key:
            index = 0
            while True:
                try:
                    token = winreg.EnumKey(key, index)
                except OSError:
                    return
                index += 1
                try:
                    with winreg.OpenKey(key, token) as subkey:
                        install_dir, _ = winreg.QueryValueEx(subkey, "InstallDir")
                except OSError:
                    continue
                yield token, install_dir
    except OSError:
        # Key absent, access denied, or any other registry failure: this
        # route contributes nothing, silently -- never a traceback.
        return


def _find_via_registry() -> AedtInstallation | None:
    """The supported release if the registry lists it; otherwise the first
    other release it lists, so an unsupported install is still reported.

    Deliberately no `try`/`except` here: a raising `_registry_entries()` is
    already caught by `detect_aedt()` / `detect_unsupported_aedt()`, the only
    two callers of this function through `_find_aedt()` -- see their own
    "never raises" guard, which is where the mutation test for this failure
    mode lives.
    """
    best: AedtInstallation | None = None
    for token, install_dir in _registry_entries():
        release = _release_from_token(token)
        install_root = Path(install_dir)
        if release is None or not _is_directory(install_root):
            continue
        found = AedtInstallation(release, install_root, DetectionRoute.REGISTRY)
        if release == SUPPORTED_AEDT_RELEASE:
            return found
        if best is None:
            best = found
    return best


def _find_aedt() -> AedtInstallation | None:
    """Whatever AEDT release this machine has, supported or not -- the raw
    finding both public functions below read and filter. The first two
    routes are release-specific by construction (`ANSYSEM_ROOT252`, `v252`
    only ever point at 2025 R2), so an unsupported release can only surface
    through the registry route."""
    env_root = os.environ.get(_ENV_VARIABLE)
    if env_root and _is_directory(Path(env_root)):
        return AedtInstallation(
            SUPPORTED_AEDT_RELEASE, Path(env_root), DetectionRoute.ENVIRONMENT_VARIABLE
        )

    program_files = os.environ.get("PROGRAMFILES")
    if program_files:
        candidate = Path(program_files) / "ANSYS Inc" / _STANDARD_VERSION_DIRNAME / "AnsysEM"
        if _is_directory(candidate):
            return AedtInstallation(
                SUPPORTED_AEDT_RELEASE, candidate, DetectionRoute.STANDARD_LOCATION
            )

    return _find_via_registry()


def detect_aedt() -> AedtInstallation | None:
    """The supported AEDT release, if this machine has it. Never raises.

    Only ever returns the release `aedt_support.SUPPORTED_AEDT_RELEASE`
    names. A different release present is reported by
    `detect_unsupported_aedt()` instead, never folded into this `None`.
    """
    try:
        found = _find_aedt()
    except Exception:  # noqa: BLE001 - "never raises" is load-bearing here
        return None
    if found is not None and found.release == SUPPORTED_AEDT_RELEASE:
        return found
    return None


def detect_unsupported_aedt() -> UnsupportedAedtInstallation | None:
    """An AEDT release present but not the one this application supports.

    `None` both when nothing is installed and when the supported release is
    -- a caller that also needs "installed at all" calls `detect_aedt()` too;
    the two are deliberately not conflated into one three-state return.
    """
    try:
        found = _find_aedt()
    except Exception:  # noqa: BLE001 - "never raises" is load-bearing here
        return None
    if found is None or found.release == SUPPORTED_AEDT_RELEASE:
        return None
    return UnsupportedAedtInstallation(found.release, found.install_root, found.route)


def detect_femm() -> FemmInstallation | None:
    """FEMM 4.2, if this machine has it at its documented default location.

    Absence is normal -- FEMM is optional -- and is reported the same way as
    every other "not here": `None`, never an exception or a warning.
    """
    try:
        system_drive = os.environ.get("SYSTEMDRIVE")
        if not system_drive:
            return None
        executable = Path(system_drive) / _FEMM_RELATIVE_EXECUTABLE
        if not executable.is_file():
            return None
        return FemmInstallation(executable.parents[1], DetectionRoute.STANDARD_LOCATION)
    except OSError:
        return None
