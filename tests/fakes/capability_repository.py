from __future__ import annotations

from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from inductor_designer.simulation.capabilities import CapabilitySnapshot


class StaticCapabilityRepository:
    """Port fake: returns one snapshot for any lookup."""

    def __init__(self, snapshot: CapabilitySnapshot) -> None:
        self.snapshot = snapshot

    def snapshot_for(self, release: AedtRelease, edition: AedtEdition) -> CapabilitySnapshot:
        return self.snapshot
