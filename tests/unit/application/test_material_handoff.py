from __future__ import annotations

from dataclasses import replace

import pytest

from inductor_designer.application.services.material_handoff import (
    MaterialHandoffError,
    prepare_material_handoff,
)
from inductor_designer.application.services.material_import import new_imported_record
from inductor_designer.application.services.material_table_import import (
    MaterialTableMetadata,
    MaterialTableRow,
    import_material_rows,
)
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease, ModelDimension
from inductor_designer.domain.catalog_records import ConductorRecord, CoreRecord, ReviewStatus
from inductor_designer.domain.project import MaterialRevisionSelection
from inductor_designer.materials.identity import MaterialRef
from inductor_designer.materials.records import MaterialRecord, SeriesKind, SourceKind
from inductor_designer.materials.replay import reproduce_record
from tests.unit.domain.test_catalog_records import make_core
from tests.unit.domain.test_project import make_project


def _loss(frequency_hz: float, flux_density_t: float) -> float:
    return 2.5 * frequency_hz**1.4 * flux_density_t**2.3


def make_reproducible_material(
    *,
    ref: MaterialRef,
    include_multi_frequency_loss: bool,
) -> tuple[MaterialRecord, dict[str, bytes]]:
    rows = [
        MaterialTableRow(
            "bh-25c",
            SeriesKind.BH_CURVE,
            None,
            25.0,
            None,
            "A/m",
            "T",
            field_strength,
            flux_density,
        )
        for field_strength, flux_density in (
            (0.0, 0.0),
            (100.0, 0.02),
            (250.0, 0.05),
        )
    ]
    frequencies = (
        (10_000.0, 50_000.0)
        if include_multi_frequency_loss
        else (10_000.0,)
    )
    rows.extend(
        MaterialTableRow(
            f"loss-{int(frequency)}hz",
            SeriesKind.LOSS_TABLE,
            frequency,
            25.0,
            None,
            "T",
            "W/m3",
            flux_density,
            _loss(frequency, flux_density),
        )
        for frequency in frequencies
        for flux_density in (0.05, 0.10)
    )
    imported = import_material_rows(
        MaterialTableMetadata(
            ref=ref,
            source_url="https://example.invalid/synthetic-material",
            source_page=1,
            captured_at="2026-07-24T00:00:00+00:00",
            source_description="Synthetic handoff fixture",
        ),
        tuple(rows),
        upload_filename="synthetic-material.xlsx",
        upload_kind=SourceKind.SPREADSHEET,
        upload_bytes=b"synthetic spreadsheet provenance",
    )
    record = new_imported_record(
        imported.ref,
        series=imported.series,
        sources=imported.sources,
        created_at="2026-07-24T00:00:00+00:00",
        notes="Synthetic handoff fixture only.",
    )
    sources = dict(imported.source_files)
    assert reproduce_record(record, sources).matches
    return record, sources


class OneCoreCatalog:
    def __init__(self, core: CoreRecord) -> None:
        self.core = core

    def get_core(self, part_number: str) -> CoreRecord | None:
        return self.core if part_number == self.core.part_number else None

    def list_cores(self) -> tuple[CoreRecord, ...]:
        return (self.core,)

    def get_conductor(self, name: str) -> ConductorRecord | None:
        return None

    def list_conductor_names(self) -> tuple[str, ...]:
        return ()


HIGH_FLUX_REF = MaterialRef("Magnetics", "High Flux", "60")
HIGH_FLUX_CORE = replace(
    make_core(),
    part_number="C058071A2",
    material=HIGH_FLUX_REF,
    review_status=ReviewStatus.REVIEWED,
    reviewed_by="test",
)
HIGH_FLUX_CATALOG = OneCoreCatalog(HIGH_FLUX_CORE)


def test_handoff_rejects_material_identity_that_does_not_match_core() -> None:
    preparation_record, sources = make_reproducible_material(
        ref=MaterialRef("Magnetics", "High Flux", "60u"),
        include_multi_frequency_loss=True,
    )

    with pytest.raises(MaterialHandoffError, match="does not match"):
        prepare_material_handoff(
            make_project(),
            HIGH_FLUX_CATALOG,
            preparation_record,
            sources,
            core_part_number="C058071A2",
            bh_series_id="bh-25c",
        )


def test_handoff_rejects_record_without_reproducible_core_loss_fit() -> None:
    record, sources = make_reproducible_material(
        ref=HIGH_FLUX_REF,
        include_multi_frequency_loss=False,
    )

    with pytest.raises(MaterialHandoffError, match="Steinmetz"):
        prepare_material_handoff(
            make_project(),
            HIGH_FLUX_CATALOG,
            record,
            sources,
            core_part_number="C058071A2",
            bh_series_id="bh-25c",
        )


def test_handoff_pins_exact_reproduced_revision_and_supported_target() -> None:
    record, sources = make_reproducible_material(
        ref=HIGH_FLUX_REF,
        include_multi_frequency_loss=True,
    )

    prepared = prepare_material_handoff(
        make_project(),
        HIGH_FLUX_CATALOG,
        record,
        sources,
        core_part_number="C058071A2",
        bh_series_id="bh-25c",
    )

    assert prepared.project.target_release == AedtRelease(2025, 2)
    assert prepared.project.target_edition is AedtEdition.COMMERCIAL
    assert prepared.project.dimension_mode is ModelDimension.THREE_D
    assert len(prepared.project.materials) == 1
    assert prepared.project.materials[0].revision_id == record.revision_id
    assert prepared.project.materials[0].bh_series_id == "bh-25c"
    assert prepared.bh_point_count > 0
    assert len(prepared.loss_frequencies_hz) >= 2
    assert prepared.source_hashes == tuple(
        (source.filename, source.sha256) for source in record.sources
    )


def test_handoff_rejects_base_project_with_existing_material_selection() -> None:
    record, sources = make_reproducible_material(
        ref=HIGH_FLUX_REF,
        include_multi_frequency_loss=True,
    )
    base = replace(
        make_project(),
        materials=(
            MaterialRevisionSelection(
                record.ref,
                record.revision_id,
                record,
                "bh-25c",
            ),
        ),
    )

    with pytest.raises(
        MaterialHandoffError,
        match="must not already contain material revisions",
    ):
        prepare_material_handoff(
            base,
            HIGH_FLUX_CATALOG,
            record,
            sources,
            core_part_number="C058071A2",
            bh_series_id="bh-25c",
        )
