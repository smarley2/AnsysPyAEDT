from __future__ import annotations

from typing import Protocol

from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from inductor_designer.simulation.capabilities import CapabilitySnapshot


class CapabilityRepository(Protocol):
    def snapshot_for(self, release: AedtRelease, edition: AedtEdition) -> CapabilitySnapshot: ...
