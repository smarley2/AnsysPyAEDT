from pathlib import Path

import pytest

from inductor_designer.adapters.pyaedt.gateway import PyaedtGateway
from inductor_designer.application.ports.aedt_gateway import AedtProbeRequest
from inductor_designer.simulation.capabilities import AedtEdition, AedtRelease


class FakeDesktop:
    def __init__(self, student_version: bool) -> None:
        self.student_version = student_version


class FakeModeler:
    def __init__(
        self,
        creation_result: object = True,
        creation_error: Exception | None = None,
    ) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
        self.creation_result = creation_result
        self.creation_error = creation_error

    def create_rectangle(self, *args: object, **kwargs: object) -> object:
        self.calls.append(("create_rectangle", args, kwargs))
        if self.creation_error is not None:
            raise self.creation_error
        return self.creation_result

    def create_box(self, *args: object, **kwargs: object) -> object:
        self.calls.append(("create_box", args, kwargs))
        if self.creation_error is not None:
            raise self.creation_error
        return self.creation_result


class FakeApp:
    def __init__(
        self,
        creation_result: object = True,
        creation_error: Exception | None = None,
        save_error: Exception | None = None,
        aedt_version_id: str = "2025.1",
        desktop_install_dir: str = r"C:\Program Files\ANSYS Inc\v252\AnsysEM",
        student_version: bool = False,
    ) -> None:
        self.modeler = FakeModeler(creation_result, creation_error)
        self.aedt_version_id = aedt_version_id
        self.desktop_install_dir = desktop_install_dir
        self.desktop_class = FakeDesktop(student_version)
        self.saved_paths: list[str] = []
        self.released = False
        self.save_error = save_error

    def save_project(self, path: str) -> bool:
        self.saved_paths.append(path)
        if self.save_error is not None:
            raise self.save_error
        return True

    def release_desktop(self, close_projects: bool, close_desktop: bool) -> None:
        assert close_projects and close_desktop
        self.released = True


class FakeFactory:
    pyaedt_version = "test-version"

    def __init__(
        self,
        creation_results: tuple[object, object] = (True, True),
        creation_errors: tuple[Exception | None, Exception | None] = (None, None),
        save_errors: tuple[Exception | None, Exception | None] = (None, None),
        observed_releases: tuple[str, str] = ("2025.1", "2025.1"),
        observed_student_versions: tuple[bool, bool] = (False, False),
    ) -> None:
        self.apps: list[tuple[str, dict[str, object], FakeApp]] = []
        self.creation_results = creation_results
        self.creation_errors = creation_errors
        self.save_errors = save_errors
        self.observed_releases = observed_releases
        self.observed_student_versions = observed_student_versions

    def create(self, dimension: str, **kwargs: object) -> FakeApp:
        app_index = len(self.apps)
        app = FakeApp(
            creation_result=self.creation_results[app_index],
            creation_error=self.creation_errors[app_index],
            save_error=self.save_errors[app_index],
            aedt_version_id=self.observed_releases[app_index],
            student_version=self.observed_student_versions[app_index],
        )
        self.apps.append((dimension, kwargs, app))
        return app


class FalsyFactory(FakeFactory):
    def __bool__(self) -> bool:
        return False


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

    assert [(dimension, kwargs) for dimension, kwargs, _ in factory.apps] == [
        (
            "2d",
            {
                "project": str(tmp_path / "probe2d.aedt"),
                "design": "CompatibilityProbe2D",
                "solution_type": "Magnetostatic",
                "version": "2024.2",
                "non_graphical": False,
                "new_desktop": True,
                "close_on_exit": False,
                "student_version": True,
            },
        ),
        (
            "3d",
            {
                "project": str(tmp_path / "probe3d.aedt"),
                "design": "CompatibilityProbe3D",
                "solution_type": "Magnetostatic",
                "version": "2024.2",
                "non_graphical": False,
                "new_desktop": True,
                "close_on_exit": False,
                "student_version": True,
            },
        ),
    ]
    assert factory.apps[0][2].modeler.calls == [
        (
            "create_rectangle",
            (),
            {
                "origin": ["0mm", "0mm", "0mm"],
                "sizes": ["10mm", "5mm"],
                "name": "CompatibilityProbeRectangle",
            },
        )
    ]
    assert factory.apps[1][2].modeler.calls == [
        (
            "create_box",
            (),
            {
                "origin": ["0mm", "0mm", "0mm"],
                "sizes": ["10mm", "5mm", "2mm"],
                "name": "CompatibilityProbeBox",
            },
        )
    ]
    assert [app.saved_paths for _, _, app in factory.apps] == [
        [str(tmp_path / "probe2d.aedt")],
        [str(tmp_path / "probe3d.aedt")],
    ]
    assert all(app.released for _, _, app in factory.apps)
    assert all(artifact.saved for artifact in result.artifacts)
    assert [artifact.project_path for artifact in result.artifacts] == [
        tmp_path / "probe2d.aedt",
        tmp_path / "probe3d.aedt",
    ]
    assert result.capabilities.include_dc_fields_3d is None
    assert result.requested_release == AedtRelease.parse("2024.2")
    assert result.requested_edition is AedtEdition.STUDENT
    assert [artifact.observed_release for artifact in result.artifacts] == [
        AedtRelease.parse("2025.2"),
        AedtRelease.parse("2025.2"),
    ]
    assert [artifact.observed_edition for artifact in result.artifacts] == [
        AedtEdition.COMMERCIAL,
        AedtEdition.COMMERCIAL,
    ]
    assert result.capabilities.release == AedtRelease.parse("2025.2")
    assert result.capabilities.edition is AedtEdition.COMMERCIAL


def test_probe_reports_failed_primitive_creation(tmp_path: Path) -> None:
    factory = FakeFactory(creation_results=(False, False))
    request = AedtProbeRequest(
        release=AedtRelease.parse("2024.2"),
        edition=AedtEdition.COMMERCIAL,
        non_graphical=True,
        output_directory=tmp_path,
    )

    result = PyaedtGateway(factory).run_probe(request)

    assert [artifact.created for artifact in result.artifacts] == [False, False]
    assert [artifact.message for artifact in result.artifacts] == [
        "Trivial Maxwell primitive creation failed; project save requested.",
        "Trivial Maxwell primitive creation failed; project save requested.",
    ]


def test_probe_uses_falsy_injected_factory(tmp_path: Path) -> None:
    factory = FalsyFactory()
    request = AedtProbeRequest(
        release=AedtRelease.parse("2024.2"),
        edition=AedtEdition.COMMERCIAL,
        non_graphical=True,
        output_directory=tmp_path,
    )

    result = PyaedtGateway(factory).run_probe(request)

    assert result.pyaedt_version == "test-version"
    assert [entry[0] for entry in factory.apps] == ["2d", "3d"]


def test_probe_releases_desktop_when_geometry_creation_raises(tmp_path: Path) -> None:
    factory = FakeFactory(
        creation_errors=(RuntimeError("geometry creation failed"), None)
    )
    request = AedtProbeRequest(
        release=AedtRelease.parse("2024.2"),
        edition=AedtEdition.COMMERCIAL,
        non_graphical=True,
        output_directory=tmp_path,
    )

    with pytest.raises(RuntimeError, match="geometry creation failed"):
        PyaedtGateway(factory).run_probe(request)

    assert len(factory.apps) == 1
    assert factory.apps[0][2].released
    assert factory.apps[0][2].saved_paths == []


def test_probe_releases_desktop_when_save_raises(tmp_path: Path) -> None:
    factory = FakeFactory(save_errors=(RuntimeError("project save failed"), None))
    request = AedtProbeRequest(
        release=AedtRelease.parse("2024.2"),
        edition=AedtEdition.COMMERCIAL,
        non_graphical=True,
        output_directory=tmp_path,
    )

    with pytest.raises(RuntimeError, match="project save failed"):
        PyaedtGateway(factory).run_probe(request)

    assert len(factory.apps) == 1
    assert factory.apps[0][2].released
    assert factory.apps[0][2].saved_paths == [str(tmp_path / "probe2d.aedt")]
