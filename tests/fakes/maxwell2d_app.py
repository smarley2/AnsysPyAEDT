from __future__ import annotations

from typing import Any

from tests.fakes.maxwell3d_app import (  # reuse recorder pieces
    FakeMaxwell3dApp,
)


class FakeMaxwell2dApp(FakeMaxwell3dApp):
    """2D recorder: same duck-typed surface plus model_depth capture."""

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "model_depth" and hasattr(self, "calls"):
            self.calls.append(("set.model_depth", {"value": value}))
        super().__setattr__(name, value)


class FakeMaxwell2dAppFactory:
    pyaedt_version = "fake-pyaedt"

    def __init__(self, app: FakeMaxwell2dApp) -> None:
        self.app = app
        self.create_kwargs: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> FakeMaxwell2dApp:
        self.create_kwargs.append(kwargs)
        return self.app
