"""The project a launch with no ``--project`` opens.

Design: ``docs/superpowers/specs/2026-09-03-blank-project-on-launch-design.md``.

Pure: domain types and ``uuid`` only, no catalog, filesystem or Qt, so the
defaults can be asserted without a window. They live in the application layer
beside the other services rather than in ``domain``, because what a new
project starts as is product policy, not a description of an inductor.
"""

from __future__ import annotations

from uuid import uuid4

from inductor_designer.domain.project import (
    Design,
    InductorProject,
    MeshIntent,
    OperatingPoint,
    RequestedOutput,
    SimulationRecipe,
    WindingOperatingPoint,
)
from inductor_designer.domain.winding import (
    ConductorMode,
    CurrentDirection,
    ToroidPlacement,
    WindingDefinition,
    WindingDirection,
)

#: Pinned rather than read from the catalog, so the default never shifts when
#: a conductor is added to the index -- the first name in
#: ``list_conductor_names()`` is whatever sorts first, which a thinner wire
#: would silently take over. This is the gauge this repository's own fixtures
#: wind with; `tests/unit/application/test_new_project.py` pins that the built
#: index actually carries it, which is the safety reading the catalog gave.
BLANK_CONDUCTOR_NAME = "AWG 18"


def new_project() -> InductorProject:
    """A blank, unsaved project: no core, one winding, nothing excited.

    No core, because selecting one is the user's first act and a preselected
    core reads as a recommendation nobody made. One winding rather than none,
    because `GuidedStudioController.addWinding` grows the list by copying its
    last entry and refuses when there is nothing to copy -- a zero-winding
    project could never grow its first winding.

    Nothing here is a new physical assumption: the frequency and both
    temperatures are the values this repository already treats as its
    defaults, and the currents are zero.
    """
    winding = WindingDefinition(
        winding_id="w1",
        label="Winding 1",
        turns=1,
        conductor_name=BLANK_CONDUCTOR_NAME,
        mode=ConductorMode.SOLID,
        # One winding around the whole toroid, which is what a single-winding
        # inductor is. `addWinding` then refuses a second winding until this
        # sector is reduced, and its refusal says exactly that.
        placement=ToroidPlacement(start_angle_deg=0.0, sector_deg=360.0),
        min_spacing_m=0.0002,
        min_clearance_m=0.001,
        winding_direction=WindingDirection.CLOCKWISE,
        terminal_intent="",
    )
    return InductorProject(
        # Dashed, not `.hex`: `schemas/project/v5.schema.json` declares
        # `projectId` as `format: uuid`, and `ProjectRepository.save` rejects
        # the 32-character form outright.
        project_id=str(uuid4()),
        name="Untitled inductor",
        description="",
        design=Design(
            core=None,
            windings=(winding,),
            core_material=None,
            manual_material_compatibility_acknowledged=False,
        ),
        operating_point=OperatingPoint(
            frequency_hz=100_000.0,
            windings=(
                WindingOperatingPoint(
                    winding_id=winding.winding_id,
                    ac_rms_current_a=0.0,
                    ac_phase_deg=0.0,
                    dc_current_a=0.0,
                    current_direction=CurrentDirection.FORWARD,
                ),
            ),
        ),
        simulation_recipe=SimulationRecipe(
            mesh_intent=MeshIntent.STANDARD,
            maximum_passes=10,
            percent_error=1.0,
            requested_outputs=(
                RequestedOutput.RESISTANCE,
                RequestedOutput.INDUCTANCE,
            ),
        ),
    )
