from pathlib import Path

from inductor_designer.application.ports.aedt_gateway import AedtProbeRequest
from inductor_designer.simulation.capabilities import AedtEdition, AedtRelease
from tests.fakes.aedt_gateway import RecordingAedtGateway


def test_recording_gateway_returns_both_dimensions_in_stable_order(tmp_path: Path) -> None:
    request = AedtProbeRequest(
        release=AedtRelease.parse("2024.2"),
        edition=AedtEdition.STUDENT,
        non_graphical=False,
        output_directory=tmp_path,
    )
    gateway = RecordingAedtGateway()

    result = gateway.run_probe(request)

    assert gateway.requests == [request]
    assert [artifact.dimension.value for artifact in result.artifacts] == ["2d", "3d"]
    assert all(artifact.created and artifact.saved for artifact in result.artifacts)
    assert result.requested_release == request.release
    assert result.requested_edition == request.edition
    assert all(artifact.observed_release == request.release for artifact in result.artifacts)
    assert all(artifact.observed_edition == request.edition for artifact in result.artifacts)
