from pathlib import Path

from inductor_designer.adapters.pyaedt.gateway import PyaedtGateway
from inductor_designer.application.ports.aedt_gateway import AedtProbeRequest
from inductor_designer.simulation.capabilities import AedtEdition, AedtRelease


class FakeModeler:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def create_rectangle(self, *args: object, **kwargs: object) -> object:
        self.calls.append(("create_rectangle", args, kwargs))
        return object()

    def create_box(self, *args: object, **kwargs: object) -> object:
        self.calls.append(("create_box", args, kwargs))
        return object()


class FakeApp:
    def __init__(self) -> None:
        self.modeler = FakeModeler()
        self.saved_paths: list[str] = []
        self.released = False

    def save_project(self, path: str) -> bool:
        self.saved_paths.append(path)
        return True

    def release_desktop(self, close_projects: bool, close_desktop: bool) -> None:
        assert close_projects and close_desktop
        self.released = True


class FakeFactory:
    pyaedt_version = "test-version"

    def __init__(self) -> None:
        self.apps: list[tuple[str, dict[str, object], FakeApp]] = []

    def create(self, dimension: str, **kwargs: object) -> FakeApp:
        app = FakeApp()
        self.apps.append((dimension, kwargs, app))
        return app


def test_probe_creates_and_saves_2d_and_3d_projects(tmp_path: Path) -> None:
    factory = FakeFactory()
    gateway = PyaedtGateway(factory)
    request = AedtProbeRequest(
        release=AedtRelease.parse("2024.2"),
        edition=AedtEdition.STUDENT,
        non_graphical=False,
        output_directory=tmp_path,
    )

    result = gateway.run_probe(request)

    assert [entry[0] for entry in factory.apps] == ["2d", "3d"]
    assert all(entry[1]["student_version"] is True for entry in factory.apps)
    assert factory.apps[0][2].modeler.calls[0][0] == "create_rectangle"
    assert factory.apps[1][2].modeler.calls[0][0] == "create_box"
    assert all(app.released for _, _, app in factory.apps)
    assert all(artifact.saved for artifact in result.artifacts)
    assert result.capabilities.include_dc_fields_3d is None
