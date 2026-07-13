from __future__ import annotations

from importlib.metadata import version
from typing import Any, Protocol, cast

from inductor_designer.application.ports.aedt_gateway import (
    AedtProbeRequest,
    AedtProbeResult,
    ProbeArtifact,
)
from inductor_designer.simulation.capabilities import CapabilitySnapshot, ModelDimension


class MaxwellApp(Protocol):
    modeler: Any

    def save_project(self, path: str) -> bool: ...

    def release_desktop(self, close_projects: bool, close_desktop: bool) -> None: ...


class MaxwellAppFactory(Protocol):
    pyaedt_version: str

    def create(self, dimension: str, **kwargs: object) -> MaxwellApp: ...


class DefaultMaxwellAppFactory:
    @property
    def pyaedt_version(self) -> str:
        return version("pyaedt")

    def create(self, dimension: str, **kwargs: object) -> MaxwellApp:
        from ansys.aedt.core import Maxwell2d, Maxwell3d

        app_class = Maxwell2d if dimension == "2d" else Maxwell3d
        return cast(MaxwellApp, app_class(**kwargs))


class PyaedtGateway:
    def __init__(self, app_factory: MaxwellAppFactory | None = None) -> None:
        self._factory = DefaultMaxwellAppFactory() if app_factory is None else app_factory

    def run_probe(self, request: AedtProbeRequest) -> AedtProbeResult:
        request.output_directory.mkdir(parents=True, exist_ok=True)
        artifacts = (
            self._create_design(request, ModelDimension.TWO_D),
            self._create_design(request, ModelDimension.THREE_D),
        )
        return AedtProbeResult(
            release=request.release,
            edition=request.edition,
            pyaedt_version=self._factory.pyaedt_version,
            capabilities=CapabilitySnapshot(
                release=request.release,
                edition=request.edition,
                include_dc_fields_3d=None,
                discovered_limits=(),
                evidence_source="trivial-design-spike",
            ),
            artifacts=artifacts,
        )

    def _create_design(
        self,
        request: AedtProbeRequest,
        dimension: ModelDimension,
    ) -> ProbeArtifact:
        project_path = request.output_directory / f"probe-{dimension.value}.aedt"
        app = self._factory.create(
            dimension.value,
            project=str(project_path),
            design=f"CompatibilityProbe{dimension.value.upper()}",
            solution_type="Magnetostatic",
            version=str(request.release),
            non_graphical=request.non_graphical,
            new_desktop=True,
            close_on_exit=False,
            student_version=request.edition.value == "student",
        )
        try:
            if dimension is ModelDimension.TWO_D:
                created = bool(
                    app.modeler.create_rectangle(
                        origin=["0mm", "0mm", "0mm"],
                        sizes=["10mm", "5mm"],
                        name="CompatibilityProbeRectangle",
                    )
                )
            else:
                created = bool(
                    app.modeler.create_box(
                        origin=["0mm", "0mm", "0mm"],
                        sizes=["10mm", "5mm", "2mm"],
                        name="CompatibilityProbeBox",
                    )
                )
            saved = bool(app.save_project(str(project_path)))
            return ProbeArtifact(
                dimension=dimension,
                project_path=project_path,
                created=created,
                saved=saved,
                message="Trivial Maxwell design created and save requested.",
            )
        finally:
            app.release_desktop(close_projects=True, close_desktop=True)
