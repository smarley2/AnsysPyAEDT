from __future__ import annotations

from inductor_designer.domain.project import RequestedOutput
from inductor_designer.simulation.raw_results import RawFieldSection, RawScalarResults
from inductor_designer.simulation.result_vocabulary import (
    FIELD_QUANTITIES,
    SCALAR_QUANTITIES,
    conductor_section_scope,
    core_section_scope,
    unit_for,
)


def test_field_quantities_are_separate_from_the_scalar_set() -> None:
    assert set(FIELD_QUANTITIES) == {
        RequestedOutput.FLUX_DENSITY,
        RequestedOutput.CURRENT_DENSITY,
    }
    assert not set(FIELD_QUANTITIES) & set(SCALAR_QUANTITIES)


def test_field_units_are_si() -> None:
    assert unit_for(RequestedOutput.FLUX_DENSITY) == "T"
    assert unit_for(RequestedOutput.CURRENT_DENSITY) == "A/m^2"


def test_section_scopes_carry_the_section_identifier() -> None:
    assert core_section_scope("core.00.span-start") == "core.section.core.00.span-start"
    assert conductor_section_scope("w1", "winding.w1.turn04.inner-bore") == (
        "winding.w1.section.winding.w1.turn04.inner-bore"
    )


def test_a_raw_field_section_may_report_nothing() -> None:
    section = RawFieldSection(
        section_id="core.00.span-start",
        scope="core.section.core.00.span-start",
        area_m2=1e-4,
        mean=None,
        maximum=None,
        diagnostic="field calculator returned no data",
    )

    assert section.mean is None
    assert section.maximum is None
    assert section.diagnostic


def test_raw_results_default_to_no_field_sections() -> None:
    raw = RawScalarResults()

    assert raw.flux_density_sections == ()
    assert raw.current_density_sections == ()
