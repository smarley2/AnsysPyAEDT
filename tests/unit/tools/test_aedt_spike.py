import json
from dataclasses import replace
from pathlib import Path

import pytest

from inductor_designer.application.ports.aedt_gateway import (
    AedtProbeRequest,
    AedtProbeResult,
)
from inductor_designer.simulation.capabilities import (
    AedtEdition,
    AedtRelease,
    ModelDimension,
)
from tests.fakes.aedt_gateway import RecordingAedtGateway
from tools.aedt_spike import main, run_spike


class RecordingStatusGateway(RecordingAedtGateway):
    def __init__(self, *, created: bool, saved: bool) -> None:
        super().__init__()
        self.created = created
        self.saved = saved

    def run_probe(self, request: AedtProbeRequest) -> AedtProbeResult:
        result = super().run_probe(request)
        first_artifact = replace(
            result.artifacts[0],
            created=self.created,
            saved=self.saved,
        )
        return replace(result, artifacts=(first_artifact, result.artifacts[1]))


class RecordingDimensionsGateway(RecordingAedtGateway):
    def __init__(self, dimensions: tuple[ModelDimension, ...]) -> None:
        super().__init__()
        self.dimensions = dimensions

    def run_probe(self, request: AedtProbeRequest) -> AedtProbeResult:
        result = super().run_probe(request)
        artifacts_by_dimension = {
            artifact.dimension: artifact for artifact in result.artifacts
        }
        return replace(
            result,
            artifacts=tuple(
                artifacts_by_dimension[dimension] for dimension in self.dimensions
            ),
        )


class RaisingGateway:
    def run_probe(self, request: AedtProbeRequest) -> AedtProbeResult:
        raise RuntimeError("probe failed before evidence serialization")


def spike_args(tmp_path: Path) -> list[str]:
    return [
        "--release",
        "2024.2",
        "--edition",
        "student",
        "--output-directory",
        str(tmp_path / "projects"),
        "--evidence",
        str(tmp_path / "evidence.json"),
    ]


def test_run_spike_writes_reviewable_evidence(tmp_path: Path) -> None:
    evidence_path = tmp_path / "evidence.json"
    request = AedtProbeRequest(
        release=AedtRelease.parse("2024.2"),
        edition=AedtEdition.COMMERCIAL,
        non_graphical=True,
        output_directory=tmp_path / "projects",
    )

    evidence = run_spike(RecordingAedtGateway(), request, evidence_path)

    expected = {
        "schemaVersion": 2,
        "requestedEnvironment": {
            "aedtRelease": "2024.2",
            "edition": "commercial",
        },
        "pyaedtVersion": "recording-fake",
        "capabilities": {
            "observed3dSession": {
                "aedtRelease": "2024.2",
                "edition": "commercial",
            },
            "includeDcFields3d": None,
            "discoveredLimits": [],
            "evidenceSource": "recording-fake",
            "reviewStatus": "unreviewed",
        },
        "manualReview": {
            "includeDcFields3d": None,
            "discoveredLimits": [],
            "reviewedBy": None,
            "reviewedAt": None,
        },
        "artifacts": [
            {
                "dimension": "2d",
                "projectFile": "probe-2d.aedt",
                "observedSession": {
                    "aedtRelease": "2024.2",
                    "edition": "commercial",
                },
                "created": True,
                "saved": True,
                "message": "recorded without launching AEDT",
            },
            {
                "dimension": "3d",
                "projectFile": "probe-3d.aedt",
                "observedSession": {
                    "aedtRelease": "2024.2",
                    "edition": "commercial",
                },
                "created": True,
                "saved": True,
                "message": "recorded without launching AEDT",
            },
        ],
    }
    assert evidence == expected
    assert evidence_path.read_text(encoding="utf-8") == json.dumps(expected, indent=2) + "\n"


def test_run_spike_removes_stale_evidence_before_gateway_failure(tmp_path: Path) -> None:
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text('{"staleSuccess": true}\n', encoding="utf-8")
    request = AedtProbeRequest(
        release=AedtRelease.parse("2024.2"),
        edition=AedtEdition.COMMERCIAL,
        non_graphical=True,
        output_directory=tmp_path / "projects",
    )

    with pytest.raises(RuntimeError, match="probe failed before evidence serialization"):
        run_spike(RaisingGateway(), request, evidence_path)

    assert not evidence_path.exists()


def test_main_returns_zero_for_created_and_saved_artifacts(tmp_path: Path) -> None:
    gateway = RecordingAedtGateway()

    exit_code = main([*spike_args(tmp_path), "--graphical"], gateway=gateway)

    assert exit_code == 0
    assert gateway.requests == [
        AedtProbeRequest(
            release=AedtRelease.parse("2024.2"),
            edition=AedtEdition.STUDENT,
            non_graphical=False,
            output_directory=tmp_path / "projects",
        )
    ]


@pytest.mark.parametrize(
    ("created", "saved"),
    [(False, True), (True, False)],
    ids=["not-created", "not-saved"],
)
def test_main_returns_nonzero_for_incomplete_artifact(
    tmp_path: Path,
    created: bool,
    saved: bool,
) -> None:
    gateway = RecordingStatusGateway(created=created, saved=saved)

    exit_code = main(spike_args(tmp_path), gateway=gateway)

    assert exit_code == 1
    evidence = json.loads((tmp_path / "evidence.json").read_text(encoding="utf-8"))
    assert evidence["artifacts"][0]["created"] is created
    assert evidence["artifacts"][0]["saved"] is saved


@pytest.mark.parametrize(
    "dimensions",
    [
        (),
        (ModelDimension.TWO_D,),
        (ModelDimension.TWO_D, ModelDimension.THREE_D, ModelDimension.THREE_D),
    ],
    ids=["empty", "missing-3d", "duplicate-3d"],
)
def test_main_returns_nonzero_without_exactly_one_artifact_per_dimension(
    tmp_path: Path,
    dimensions: tuple[ModelDimension, ...],
) -> None:
    gateway = RecordingDimensionsGateway(dimensions)

    exit_code = main(spike_args(tmp_path), gateway=gateway)

    assert exit_code == 1
