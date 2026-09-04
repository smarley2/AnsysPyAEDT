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
    ManualECoreSelection,
)
from inductor_designer.geometry.ecore.body import FinishedECore
from inductor_designer.geometry.ecore.reluctance import referred_lengths
from inductor_designer.geometry.toroid.packing import PackedWinding
from inductor_designer.simulation.preliminary import PreliminaryRequest
from inductor_designer.simulation.preliminary_contracts import CoreMagneticProperties

MANUAL_ECORE_NETWORK_NOTE = (
    "Manual E-core reluctance is summed section by section from the entered "
    "dimensions -- centre leg, both yokes, and the two outer legs in parallel "
    "-- and reduced to an iron length and a gap length referred to the "
    "centre-leg area A_e = F * C. Flux comes from that network rather than "
    "from ampere-turns over a path length, because with a gap most of the "
    "ampere-turns drop across the gap. Fringing is excluded, which understates "
    "reluctance and so OVERSTATES inductance, by more as the gap grows; a "
    "solved run is what shows the difference. Manufacturer effective values "
    "and an inductance factor are not available for a Manual core."
)
MANUAL_ECORE_UNGAPPED_NOTE = (
    "Manual E-core reluctance is summed section by section from the entered "
    "dimensions -- centre leg, both yokes, and the two outer legs in parallel "
    "-- referred to the centre-leg area A_e = F * C. The pair is ungapped, so "
    "no gap term applies. Manufacturer effective values and an inductance "
    "factor are not available for a Manual core."
)
MANUAL_CORE_PATH_NOTE = (
    "Manual-core magnetic path length and volume are computed from the entered "
    "toroid dimensions as l_e = pi * (outer diameter + inner diameter) / 2, "
    "A_e = ((outer diameter - inner diameter) / 2) * height, and "
    "V_e = A_e * l_e. Manufacturer effective values are not available for a "
    "Manual core. A_e is the full rectangular cross-section: the corner radius "
    "that the modeled geometry rounds is not subtracted, so A_e, and every "
    "inductance derived from it, is slightly optimistic for a rounded core."
)
CATALOG_OVERRIDE_NOTE = (
    "Core dimension overrides change the modeled geometry but not the "
    "manufacturer's effective magnetic path length, area, volume, or "
    "inductance factor, which are used here as recorded in the catalog. The "
    "reported A_L deviation therefore does not reflect the overrides."
)


def core_magnetic_properties(
    core: CoreSelection | None,
) -> CoreMagneticProperties | None:
    """The path length and volume the estimator needs, and their provenance."""
    if core is None:
        return None
    if isinstance(core, ManualECoreSelection):
        # The reluctance network, reduced to the two lengths the estimate
        # needs (geometry/ecore/reluctance.py). Both are referred to the
        # centre-leg area, which is also the area flux density is quoted
        # against, by convention.
        body = FinishedECore(
            centre_leg_width_m=core.centre_leg_width_m,
            depth_m=core.depth_m,
            window_width_m=core.window_width_m,
            window_height_m=core.window_height_m,
            outer_leg_width_m=core.outer_leg_width_m,
            yoke_thickness_m=core.yoke_thickness_m,
            gaps=core.gaps_m,
            gap_spacings_m=core.gap_spacings_m,
            outer_legs_gapped=core.outer_legs_gapped,
        )
        lengths = referred_lengths(body)
        return CoreMagneticProperties(
            path_length_m=lengths.iron_m,
            volume_m3=lengths.iron_volume_m3,
            effective_area_m2=lengths.effective_area_m2,
            gap_length_m=lengths.gap_m,
            # A manual core has no manufacturer inductance factor, so the A_L
            # check has no reference and reports itself unavailable -- the
            # same as a manual toroid.
            al_value_nh=None,
            notes=(MANUAL_ECORE_NETWORK_NOTE,)
            if lengths.gap_m > 0.0
            else (MANUAL_ECORE_UNGAPPED_NOTE,),
        )
    if isinstance(core, ManualCoreSelection):
        path_length_m = math.pi * (core.outer_diameter_m + core.inner_diameter_m) / 2.0
        effective_area_m2 = (
            (core.outer_diameter_m - core.inner_diameter_m) / 2.0
        ) * core.height_m
        return CoreMagneticProperties(
            path_length_m=path_length_m,
            volume_m3=effective_area_m2 * path_length_m,
            effective_area_m2=effective_area_m2,
            # A Manual core has no manufacturer inductance factor, so the A_L
            # check has no reference and reports itself unavailable.
            al_value_nh=None,
            notes=(MANUAL_CORE_PATH_NOTE,),
        )
    assert isinstance(core, CatalogCoreSelection)
    return CoreMagneticProperties(
        path_length_m=core.snapshot.path_length_m,
        volume_m3=core.snapshot.volume_m3,
        effective_area_m2=core.snapshot.effective_area_m2,
        al_value_nh=core.snapshot.al_value_nh,
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
