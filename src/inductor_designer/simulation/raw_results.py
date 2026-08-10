"""What a backend reported, before any normalization.

Every field is optional: ``None`` means the backend did not report the
quantity, which the normalizer turns into an explicit unavailable reason
rather than a zero.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RawWindingResult:
    winding_id: str
    resistance_ohm: float | None = None
    inductance_h: float | None = None
    impedance: complex | None = None


@dataclass(frozen=True, slots=True)
class RawMatrix:
    kind: str
    labels: tuple[str, ...]
    values: tuple[tuple[float, ...], ...]

    def __post_init__(self) -> None:
        size = len(self.labels)
        if len(self.values) != size or any(len(row) != size for row in self.values):
            raise ValueError("a reported matrix must be square against its labels")


@dataclass(frozen=True, slots=True)
class RawConvergence:
    passes: tuple[tuple[int, float], ...]
    converged: bool | None = None


@dataclass(frozen=True, slots=True)
class RawFieldSection:
    """One evaluated area: a 3D cross section, or a 2D region.

    ``mean`` is the area-weighted mean of the field magnitude over ``area_m2``;
    a volume average never appears here. ``None`` with a ``diagnostic`` means
    this one area failed to evaluate while its neighbours may have succeeded.
    """

    section_id: str
    scope: str
    area_m2: float
    mean: float | None
    maximum: float | None
    diagnostic: str | None = None


@dataclass(frozen=True, slots=True)
class RawScalarResults:
    windings: tuple[RawWindingResult, ...] = ()
    matrices: tuple[RawMatrix, ...] = ()
    copper_loss_w: float | None = None
    core_loss_w: float | None = None
    total_loss_w: float | None = None
    magnetic_energy_j: float | None = None
    convergence: RawConvergence | None = None
    solver_status: str | None = None
    diagnostics: tuple[str, ...] = ()
    flux_density_sections: tuple[RawFieldSection, ...] = ()
    current_density_sections: tuple[RawFieldSection, ...] = ()
