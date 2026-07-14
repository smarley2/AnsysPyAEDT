from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from inductor_designer.domain.catalog_records import (
    ConductorRecord,
    ConductorStandard,
    CoreFamily,
    CoreRecord,
    Dimension,
    ReviewStatus,
)
from inductor_designer.materials.identity import MaterialRef


def _dimension_to_json(dimension: Dimension) -> dict[str, object]:
    return {"nominalM": dimension.nominal_m, "minM": dimension.min_m, "maxM": dimension.max_m}


def _dimension_from_json(data: Mapping[str, Any]) -> Dimension:
    return Dimension(nominal_m=data["nominalM"], min_m=data["minM"], max_m=data["maxM"])


def core_record_to_json(record: CoreRecord) -> dict[str, object]:
    return {
        "manufacturer": record.manufacturer,
        "family": record.family.value,
        "partNumber": record.part_number,
        "material": {
            "manufacturer": record.material.manufacturer,
            "name": record.material.name,
            "grade": record.material.grade,
        },
        "coating": record.coating,
        "catalogRevision": record.catalog_revision,
        "sourceUrl": record.source_url,
        "sourcePage": record.source_page,
        "outerDiameter": _dimension_to_json(record.outer_diameter),
        "innerDiameter": _dimension_to_json(record.inner_diameter),
        "height": _dimension_to_json(record.height),
        "effectiveAreaM2": record.effective_area_m2,
        "pathLengthM": record.path_length_m,
        "volumeM3": record.volume_m3,
        "alValueNh": record.al_value_nh,
        "reviewStatus": record.review_status.value,
        "reviewedBy": record.reviewed_by,
    }


def core_record_from_json(data: Mapping[str, Any]) -> CoreRecord:
    material = data["material"]
    return CoreRecord(
        manufacturer=data["manufacturer"],
        family=CoreFamily(data["family"]),
        part_number=data["partNumber"],
        material=MaterialRef(material["manufacturer"], material["name"], material["grade"]),
        coating=data["coating"],
        catalog_revision=data["catalogRevision"],
        source_url=data["sourceUrl"],
        source_page=data["sourcePage"],
        outer_diameter=_dimension_from_json(data["outerDiameter"]),
        inner_diameter=_dimension_from_json(data["innerDiameter"]),
        height=_dimension_from_json(data["height"]),
        effective_area_m2=data["effectiveAreaM2"],
        path_length_m=data["pathLengthM"],
        volume_m3=data["volumeM3"],
        al_value_nh=data["alValueNh"],
        review_status=ReviewStatus(data["reviewStatus"]),
        reviewed_by=data["reviewedBy"],
    )


def conductor_record_to_json(record: ConductorRecord) -> dict[str, object]:
    return {
        "name": record.name,
        "standard": record.standard.value,
        "bareDiameterM": record.bare_diameter_m,
        "grade1DiameterM": record.grade1_diameter_m,
        "grade2DiameterM": record.grade2_diameter_m,
        "source": record.source,
        "catalogRevision": record.catalog_revision,
        "reviewStatus": record.review_status.value,
        "reviewedBy": record.reviewed_by,
    }


def conductor_record_from_json(data: Mapping[str, Any]) -> ConductorRecord:
    return ConductorRecord(
        name=data["name"],
        standard=ConductorStandard(data["standard"]),
        bare_diameter_m=data["bareDiameterM"],
        grade1_diameter_m=data["grade1DiameterM"],
        grade2_diameter_m=data["grade2DiameterM"],
        source=data["source"],
        catalog_revision=data["catalogRevision"],
        review_status=ReviewStatus(data["reviewStatus"]),
        reviewed_by=data["reviewedBy"],
    )
