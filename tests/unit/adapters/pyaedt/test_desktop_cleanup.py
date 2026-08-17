from __future__ import annotations

import sys
import types

import pytest

from inductor_designer.adapters.pyaedt.desktop_cleanup import (
    release_live_app,
    release_orphaned_desktops,
)

MODULE = "ansys.aedt.core.internal.desktop_sessions"


class _Session:
    def __init__(self, fails: bool = False) -> None:
        self.released: list[dict[str, bool]] = []
        self.fails = fails

    def release_desktop(self, close_projects: bool, close_on_exit: bool) -> None:
        if self.fails:
            raise RuntimeError("session is already gone")
        self.released.append(
            {"close_projects": close_projects, "close_on_exit": close_on_exit}
        )


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> dict[str, _Session]:
    sessions: dict[str, _Session] = {}
    module = types.ModuleType(MODULE)
    module._desktop_sessions = sessions  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, MODULE, module)
    return sessions


def test_every_registered_session_is_released(registry: dict[str, _Session]) -> None:
    """A failed launch leaves a desktop nothing else will close, and the next
    launch then attaches to it instead of its own."""
    registry["55001"] = _Session()
    registry["55002"] = _Session()

    assert release_orphaned_desktops() == 2
    for session in registry.values():
        assert session.released == [{"close_projects": True, "close_on_exit": True}]


def test_a_stuck_session_does_not_stop_the_others(
    registry: dict[str, _Session],
) -> None:
    registry["55001"] = _Session(fails=True)
    registry["55002"] = _Session()

    assert release_orphaned_desktops() == 1
    assert registry["55002"].released


def test_no_registry_is_not_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, MODULE, None)

    assert release_orphaned_desktops() == 0


class _App:
    def __init__(self, fails: bool = False) -> None:
        self.calls: list[tuple[bool, bool]] = []
        self.fails = fails

    def release_desktop(self, close_projects: bool, close_desktop: bool) -> None:
        if self.fails:
            raise RuntimeError("gRPC channel is gone")
        self.calls.append((close_projects, close_desktop))


def test_a_normal_release_closes_projects_and_the_desktop(
    registry: dict[str, _Session],
) -> None:
    app = _App()

    assert release_live_app(app) is None
    assert app.calls == [(True, True)]
    # Nothing to fall back to when the direct release worked.
    assert not registry


def test_a_failed_release_falls_back_instead_of_leaking_the_seat(
    registry: dict[str, _Session],
) -> None:
    """A seat is held until the process exits, out of a pool shared with other
    users, so a release that raises must not propagate out of a `finally` block
    and leave the desktop running -- it would also mask the original failure.
    """
    registry["55001"] = _Session()
    app = _App(fails=True)

    diagnostic = release_live_app(app)

    assert diagnostic is not None
    assert "release_desktop failed" in diagnostic
    assert "released 1 registered session(s)" in diagnostic
    assert registry["55001"].released
