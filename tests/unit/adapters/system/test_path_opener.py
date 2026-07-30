from __future__ import annotations

from pathlib import Path

import pytest

from inductor_designer.adapters.system.path_opener import DesktopPathOpener


def test_opening_a_file_hands_it_to_the_shell(tmp_path: Path) -> None:
    opened: list[str] = []
    target = tmp_path / "Boost.aedt"
    target.write_text("project", encoding="utf-8")

    DesktopPathOpener(launcher=opened.append).open_path(target)

    assert opened == [str(target)]


def test_opening_a_folder_hands_it_to_the_shell(tmp_path: Path) -> None:
    opened: list[str] = []

    DesktopPathOpener(launcher=opened.append).open_path(tmp_path)

    assert opened == [str(tmp_path)]


def test_a_missing_path_is_refused_before_the_shell_is_called(tmp_path: Path) -> None:
    opened: list[str] = []

    with pytest.raises(FileNotFoundError, match="does not exist"):
        DesktopPathOpener(launcher=opened.append).open_path(tmp_path / "gone.aedt")

    assert opened == []
