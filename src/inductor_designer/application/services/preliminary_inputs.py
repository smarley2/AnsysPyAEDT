"""Assemble one `PreliminaryRequest` from a project (specification section 5).

The estimator takes records, never repositories. This service is the single
place that resolves them, so the Qt controller stays free of catalog lookups
and every resolution rule is testable without Qt.
"""

from __future__ import annotations

import math

from inductor_designer.application.ports.catalog import CatalogRepository
from inductor_designer.application.services.geometry_model import GeometryModel
from inductor_designer.domain.catalog_records import ConductorRecord
from inductor_designer.domain.project import (
    CatalogCoreSelection,
    CoreSelection,
    InductorProject,
    ManualCoreSelection,
)
from inductor_designer.geometry.packing import PackedWinding
from inductor_designer.simulation.preliminary import PreliminaryRequest
from inductor_designer.simulation.preliminary_contracts import CoreMagneticProperties

MANUAL_CORE_PATH_NOTE = (
    "Manual-core magnetic path length and volume are computed from the entered "
    "toroid dimensions as l_e = pi * (outer diameter + inner diameter) / 2, "
    "A_e = ((outer diameter - inner diameter) / 2) * height, and "
    "V_e = A_e * l_e. Manufacturer effective values are not available for a "
    "Manual core."
)
CATALOG_OVERRIDE_NOTE = (
    "Core dimension overrides change the modeled geometry but not the "
    "manufacturer's effective magnetic path length and volume, which are used "
    "here as recorded in the catalog."
)


def core_magnetic_properties(
    core: CoreSelection | None,
) -> CoreMagneticProperties | None:
    """The path length and volume the estimator needs, and their provenance."""
    if core is None:
        return None
    if isinstance(core, ManualCoreSelection):
        path_length_m = math.pi * (core.outer_diameter_m + core.inner_diameter_m) / 2.0
        effective_area_m2 = (
            (core.outer_diameter_m - core.inner_diameter_m) / 2.0
        ) * core.height_m
        return CoreMagneticProperties(
            path_length_m=path_length_m,
            volume_m3=effective_area_m2 * path_length_m,
            notes=(MANUAL_CORE_PATH_NOTE,),
        )
    assert isinstance(core, CatalogCoreSelection)
    return CoreMagneticProperties(
        path_length_m=core.snapshot.path_length_m,
        volume_m3=core.snapshot.volume_m3,
        notes=(CATALOG_OVERRIDE_NOTE,) if core.overrides else (),
    )


def build_preliminary_request(
    project: InductorProject,
    catalog: CatalogRepository,
    geometry: GeometryModel | None,
) -> PreliminaryRequest:
    """Resolve records for one estimate.

    `geometry` is None when the geometry model refused the current project. The
    request is still built: flux density, core loss, and current density do not
    depend on packing, so only wire length, resistance, and wire loss lose their
    input and the estimator reports exactly those as unavailable.
    """
    conductors: dict[str, ConductorRecord] = {}
    for winding in project.design.windings:
        record = catalog.get_conductor(winding.conductor_name)
        if record is not None:
            conductors[winding.winding_id] = record
    packings: dict[str, PackedWinding] = (
        {} if geometry is None else {item.winding_id: item for item in geometry.packings}
    )
    return PreliminaryRequest(
        project=project,
        core=core_magnetic_properties(project.design.core),
        conductors_by_winding=conductors,
        packings_by_winding=packings,
    )
