from __future__ import annotations

import re
from importlib.metadata import version
from typing import Any, Protocol, cast

from inductor_designer.application.ports.aedt_gateway import (
    AedtProbeRequest,
    AedtProbeResult,
    ProbeArtifact,
)
from inductor_designer.simulation.capabilities import (
    AedtEdition,
    AedtRelease,
    CapabilityReviewStatus,
    CapabilitySnapshot,
    ModelDimension,
)


def _release_from_install_dir(install_dir: str) -> AedtRelease:
    match = re.search(r"(?:^|[\\/])v(?P<token>\d{3})(?:[\\/]|$)", install_dir)
    if match is None:
        raise ValueError(
            f"Could not determine AEDT release from installation directory: {install_dir!r}"
        )
    token = match.group("token")
    return AedtRelease(year=2000 + int(token[:2]), release=int(token[2]))


class DesktopSession(Protocol):
    student_version: bool


class MaxwellApp(Protocol):
    modeler: Any
    aedt_version_id: str
    desktop_install_dir: str
    desktop_class: DesktopSession

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
        observed_3d = artifacts[1]
        return AedtProbeResult(
            requested_release=request.release,
            requested_edition=request.edition,
            pyaedt_version=self._factory.pyaedt_version,
            capabilities=CapabilitySnapshot(
                release=observed_3d.observed_release,
                edition=observed_3d.observed_edition,
                include_dc_fields_3d=None,
                discovered_limits=(),
                evidence_source="trivial-design-spike",
                review_status=CapabilityReviewStatus.UNREVIEWED,
            ),
            artifacts=artifacts,
        )

    def _create_design(
        self,
        request: AedtProbeRequest,
        dimension: ModelDimension,
    ) -> ProbeArtifact:
        project_path = request.output_directory / f"probe{dimension.value}.aedt"
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
            observed_release = _release_from_install_dir(str(app.desktop_install_dir))
            observed_edition = (
                AedtEdition.STUDENT
                if app.desktop_class.student_version
                else AedtEdition.COMMERCIAL
            )
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
                observed_release=observed_release,
                observed_edition=observed_edition,
                created=created,
                saved=saved,
                message=(
                    "Trivial Maxwell design created and save requested."
                    if created
                    else "Trivial Maxwell primitive creation failed; project save requested."
                ),
            )
        finally:
            app.release_desktop(close_projects=True, close_desktop=True)
