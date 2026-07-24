from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from inductor_designer.adapters.pyaedt.gateway import PyaedtGateway
from inductor_designer.application.ports.aedt_gateway import AedtGateway, AedtProbeRequest
from inductor_designer.application.services.aedt_support import (
    SUPPORTED_AEDT_EDITION,
    SUPPORTED_AEDT_RELEASE,
)
from inductor_designer.simulation.capabilities import AedtEdition, AedtRelease


def run_spike(
    gateway: AedtGateway,
    request: AedtProbeRequest,
    evidence_path: Path,
) -> dict[str, object]:
    evidence_path.unlink(missing_ok=True)
    result = gateway.run_probe(request)
    evidence: dict[str, object] = {
        "schemaVersion": 2,
        "requestedEnvironment": {
            "aedtRelease": str(result.requested_release),
            "edition": result.requested_edition.value,
        },
        "pyaedtVersion": result.pyaedt_version,
        "capabilities": {
            "observed3dSession": {
                "aedtRelease": str(result.capabilities.release),
                "edition": result.capabilities.edition.value,
            },
            "includeDcFields3d": result.capabilities.include_dc_fields_3d,
            "discoveredLimits": list(result.capabilities.discovered_limits),
            "evidenceSource": result.capabilities.evidence_source,
            "reviewStatus": result.capabilities.review_status.value,
        },
        "manualReview": {
            "includeDcFields3d": None,
            "discoveredLimits": [],
            "reviewedBy": None,
            "reviewedAt": None,
        },
        "artifacts": [
            {
                "dimension": artifact.dimension.value,
                "projectFile": artifact.project_path.name,
                "observedSession": {
                    "aedtRelease": str(artifact.observed_release),
                    "edition": artifact.observed_edition.value,
                },
                "created": artifact.created,
                "saved": artifact.saved,
                "message": artifact.message,
            }
            for artifact in result.artifacts
        ],
    }
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    return evidence


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the controlled AEDT compatibility spike.")
    parser.add_argument(
        "--release",
        required=True,
        choices=[str(SUPPORTED_AEDT_RELEASE)],
    )
    parser.add_argument(
        "--edition",
        required=True,
        choices=[SUPPORTED_AEDT_EDITION.value],
    )
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--graphical", action="store_true")
    return parser.parse_args(argv)


def _artifacts_are_complete(evidence: dict[str, object]) -> bool:
    artifacts = evidence["artifacts"]
    if not isinstance(artifacts, list) or len(artifacts) != 2:
        return False
    observed_dimensions: set[object] = set()
    for item in artifacts:
        if (
            not isinstance(item, dict)
            or item.get("created") is not True
            or item.get("saved") is not True
        ):
            return False
        observed_dimensions.add(item.get("dimension"))
    return observed_dimensions == {"2d", "3d"}


def main(
    argv: Sequence[str] | None = None,
    *,
    gateway: AedtGateway | None = None,
) -> int:
    args = parse_args(argv)
    request = AedtProbeRequest(
        release=AedtRelease.parse(args.release),
        edition=AedtEdition(args.edition),
        non_graphical=not args.graphical,
        output_directory=args.output_directory,
    )
    selected_gateway = PyaedtGateway() if gateway is None else gateway
    evidence = run_spike(selected_gateway, request, args.evidence)
    return 0 if _artifacts_are_complete(evidence) else 1


if __name__ == "__main__":
    raise SystemExit(main())
