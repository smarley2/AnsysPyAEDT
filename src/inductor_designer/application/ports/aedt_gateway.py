from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from inductor_designer.simulation.capabilities import (
    AedtEdition,
    AedtRelease,
    CapabilitySnapshot,
    ModelDimension,
)


@dataclass(frozen=True, slots=True)
class AedtProbeRequest:
    release: AedtRelease
    edition: AedtEdition
    non_graphical: bool
    output_directory: Path


@dataclass(frozen=True, slots=True)
class ProbeArtifact:
    dimension: ModelDimension
    project_path: Path
    created: bool
    saved: bool
    message: str


@dataclass(frozen=True, slots=True)
class AedtProbeResult:
    release: AedtRelease
    edition: AedtEdition
    pyaedt_version: str
    capabilities: CapabilitySnapshot
    artifacts: tuple[ProbeArtifact, ...]


class AedtGateway(Protocol):
    def run_probe(self, request: AedtProbeRequest) -> AedtProbeResult: ...
