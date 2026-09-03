"""The project a launch with no `--project` opens.

Design: `docs/superpowers/specs/2026-09-03-blank-project-on-launch-design.md`.

Every value is asserted rather than described. A default nobody looks at is
how an invented physical assumption ships: each number here is either an
existing convention in this repository (cited beside the assertion) or an
inert placeholder the user replaces on the first screen.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from inductor_designer.adapters.persistence.project_repository import ProjectRepository
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from inductor_designer.application.services.new_project import (
    BLANK_CONDUCTOR_NAME,
    new_project,
)
from inductor_designer.domain.winding import (
    ConductorMode,
    CurrentDirection,
    WindingDirection,
)

ROOT = Path(__file__).resolve().parents[3]


def test_the_blank_project_has_no_core_and_no_material() -> None:
    """Selecting a core is the user's first act. A preselected one would read
    as a recommendation nobody made."""
    project = new_project()
    assert project.design.core is None
    assert project.design.core_material is None
    assert project.design.manual_material_compatibility_acknowledged is False


def test_the_blank_project_carries_exactly_one_winding() -> None:
    """Not zero: `GuidedStudioController.addWinding` grows the list by copying
    its last entry and refuses when there is nothing to copy, so a
    zero-winding project could never grow its first winding."""
    project = new_project()
    (winding,) = project.design.windings
    assert winding.winding_id == "w1"
    assert winding.turns == 1
    assert winding.conductor_name == BLANK_CONDUCTOR_NAME
    assert winding.mode is ConductorMode.SOLID
    assert winding.start_angle_deg == 0.0
    assert winding.sector_deg == 360.0
    # The repository's existing convention, from `make_winding`.
    assert winding.min_spacing_m == 0.0002
    assert winding.min_clearance_m == 0.001
    assert winding.winding_direction is WindingDirection.CLOCKWISE

    (excitation,) = project.operating_point.windings
    assert excitation.winding_id == winding.winding_id
    assert excitation.ac_rms_current_a == 0.0
    assert excitation.ac_phase_deg == 0.0
    assert excitation.dc_current_a == 0.0
    assert excitation.current_direction is CurrentDirection.FORWARD


def test_the_blank_operating_point_and_recipe_match_the_repository_defaults() -> None:
    """100 kHz is `make_operating_point`'s default and the temperatures are
    `OperatingPoint`'s own field defaults -- this factory introduces no new
    physical assumption, and this test is what would fail if it started to."""
    project = new_project()
    assert project.operating_point.frequency_hz == 100_000.0
    assert project.operating_point.winding_temperature_c == 20.0
    assert project.operating_point.core_temperature_c == 25.0
    assert project.simulation_recipe.maximum_passes == 10
    assert project.simulation_recipe.percent_error == 1.0
    assert [output.value for output in project.simulation_recipe.requested_outputs] == [
        "resistance",
        "inductance",
    ]


def test_each_blank_project_gets_its_own_dashed_uuid() -> None:
    """`schemas/project/v5.schema.json` declares `projectId` as `format: uuid`,
    which a 32-character `uuid4().hex` does not satisfy -- a blank project
    carrying one could never be saved, and being saved is the only thing a
    blank project is for."""
    first, second = new_project(), new_project()
    assert str(UUID(first.project_id)) == first.project_id
    assert first.project_id != second.project_id


def test_the_blank_project_round_trips_through_the_real_schema(tmp_path: Path) -> None:
    """The defaults are only defaults if they survive `File > Save As`."""
    repository = ProjectRepository(SchemaRepository(ROOT / "schemas"))
    target = tmp_path / "blank.inductor.json"
    repository.save(new_project(), target)
    assert repository.load(target).design.core is None


def test_the_pinned_conductor_exists_in_the_built_catalog(tmp_path: Path) -> None:
    """A pinned gauge is only safe while the shipped index carries it. Without
    this, dropping `AWG 18` from `catalog/conductors/round-wire.yaml` would
    leave the first launch's Windings screen naming a conductor no lookup can
    resolve, and every other test in this file would stay green."""
    from inductor_designer.adapters.catalog.sqlite_repository import (
        SqliteCatalogRepository,
    )
    from tools.build_catalog import build

    index = tmp_path / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    assert BLANK_CONDUCTOR_NAME in SqliteCatalogRepository(index).list_conductor_names()
