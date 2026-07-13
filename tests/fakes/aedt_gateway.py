from pathlib import Path

from inductor_designer.application.ports.aedt_gateway import (
    AedtProbeRequest,
    AedtProbeResult,
    ProbeArtifact,
)
from inductor_designer.simulation.capabilities import (
    CapabilityReviewStatus,
    CapabilitySnapshot,
    ModelDimension,
)


class RecordingAedtGateway:
    def __init__(self) -> None:
        self.requests: list[AedtProbeRequest] = []

    def run_probe(self, request: AedtProbeRequest) -> AedtProbeResult:
        self.requests.append(request)
        artifacts = tuple(
            ProbeArtifact(
                dimension=dimension,
                project_path=Path(request.output_directory) / f"probe{dimension.value}.aedt",
                observed_release=request.release,
                observed_edition=request.edition,
                created=True,
                saved=True,
                message="recorded without launching AEDT",
            )
            for dimension in (ModelDimension.TWO_D, ModelDimension.THREE_D)
        )
        return AedtProbeResult(
            requested_release=request.release,
            requested_edition=request.edition,
            pyaedt_version="recording-fake",
            capabilities=CapabilitySnapshot(
                release=request.release,
                edition=request.edition,
                include_dc_fields_3d=None,
                discovered_limits=(),
                evidence_source="recording-fake",
                review_status=CapabilityReviewStatus.UNREVIEWED,
            ),
            artifacts=artifacts,
        )
