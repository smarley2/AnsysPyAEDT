"""Where the user's own catalog and material data lives.

Design: `docs/superpowers/specs/2026-09-04-user-core-catalog-design.md`.

The location is the whole point of these tests. An upgrade rewrites the
installed bundle, and the uninstaller only removes what it installed
(`packaging/installer.iss`), so anything the user adds has to live under the
per-user data directory or it is on a countdown.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from inductor_designer.adapters.system.environment import (
    application_data_directory,
    catalog_overlay_directory,
    seed_material_overlay,
    user_material_overlay_directory,
)


def test_the_overlay_directories_live_beside_logs_and_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert catalog_overlay_directory().parent == application_data_directory()
    assert user_material_overlay_directory().parent == application_data_directory()
    # Not inside the shipped resource root, which is what an upgrade replaces.
    assert catalog_overlay_directory().name == "catalog-overlay"
    assert user_material_overlay_directory().name == "materials-overlay"


def test_the_material_seed_is_copied_once_and_never_over_user_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The one-time guard is the entire safety of this shortcut: a second copy
    would overwrite a material the user imported with the shipped seed."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "data"))
    seed = tmp_path / "seed"
    (seed / "Magnetics" / "High_Flux").mkdir(parents=True)
    (seed / "Magnetics" / "High_Flux" / "record.json").write_text("{}", encoding="utf-8")

    assert seed_material_overlay(seed) is True
    copied = user_material_overlay_directory() / "Magnetics" / "High_Flux" / "record.json"
    assert copied.is_file()

    copied.write_text('{"mine": true}', encoding="utf-8")
    assert seed_material_overlay(seed) is False
    assert copied.read_text(encoding="utf-8") == '{"mine": true}'


def test_seeding_tolerates_a_missing_seed_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A source checkout or a stripped bundle has no seed tree; that is not a
    startup failure, it just means there is nothing to copy."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "data"))
    assert seed_material_overlay(tmp_path / "absent") is False
    assert not user_material_overlay_directory().exists()
