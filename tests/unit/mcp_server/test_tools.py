from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from inductor_designer.adapters.catalog.sqlite_repository import SqliteCatalogRepository
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from inductor_designer.mcp_server import tools
from tests.fakes.femm_solver import RecordingFemmSolver
from tests.fakes.maxwell2d_exporter import RecordingMaxwell2dExporter
from tests.fakes.maxwell_exporter import RecordingMaxwell3dExporter

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "tests" / "fixtures" / "sample_geometry_project.inductor.json"


@pytest.fixture()
def catalog_index(tmp_path: Path) -> Path:
    from tools.build_catalog import build

    index = tmp_path / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    return index


@pytest.fixture()
def context(catalog_index: Path, tmp_path: Path) -> tools.ToolContext:
    return tools.ToolContext(
        catalog=SqliteCatalogRepository(catalog_index),
        schemas=SchemaRepository(ROOT / "schemas"),
        matrix_path=ROOT / "compatibility" / "aedt-matrix.yml",
        output_root=tmp_path / "out",
        maxwell3d_exporter=RecordingMaxwell3dExporter(),
        maxwell2d_exporter=RecordingMaxwell2dExporter(),
        femm_solver=RecordingFemmSolver(),
    )


@pytest.fixture()
def document() -> dict[str, object]:
    return dict(json.loads(FIXTURE.read_text(encoding="utf-8")))


@pytest.fixture()
def document_2d(document: dict[str, object]) -> dict[str, object]:
    doc = copy.deepcopy(document)
    target = dict(doc["target"])  # type: ignore[arg-type]
    target["dimensionMode"] = "2d"
    doc["target"] = target
    return doc


def _save(context: tools.ToolContext, doc: dict[str, object], path: Path) -> None:
    result = tools.save_project(context, doc, str(path))
    assert "error" not in result, result


def test_list_cores_contains_fixture_core(context: tools.ToolContext) -> None:
    result = tools.list_cores(context)
    part_numbers = [core["partNumber"] for core in result["cores"]]  # type: ignore[union-attr]
    assert "0077071A7" in part_numbers


def test_get_core_roundtrip(context: tools.ToolContext) -> None:
    result = tools.get_core(context, "0077071A7")
    assert result["partNumber"] == "0077071A7"
    assert "error" not in result


def test_get_core_unknown_part_returns_error(context: tools.ToolContext) -> None:
    result = tools.get_core(context, "does-not-exist")
    assert "error" in result
    assert result["issues"]


def test_list_conductors_contains_awg18(context: tools.ToolContext) -> None:
    result = tools.list_conductors(context)
    assert "AWG 18" in result["conductors"]  # type: ignore[operator]


def test_save_project_happy_path(
    context: tools.ToolContext, document: dict[str, object], tmp_path: Path
) -> None:
    target = tmp_path / "saved.inductor.json"
    result = tools.save_project(context, document, str(target))
    assert result == {"path": str(target), "projectId": document["projectId"]}
    assert target.is_file()


def test_save_project_invalid_document_returns_error(
    context: tools.ToolContext, tmp_path: Path
) -> None:
    result = tools.save_project(context, {"schemaVersion": 2}, str(tmp_path / "bad.json"))
    assert "error" in result
    assert result["issues"]
    assert not (tmp_path / "bad.json").exists()


def test_validate_project_on_saved_fixture_has_no_issues(
    context: tools.ToolContext, document: dict[str, object], tmp_path: Path
) -> None:
    target = tmp_path / "saved.inductor.json"
    _save(context, document, target)
    result = tools.validate_project(context, str(target))
    assert result == {"issues": []}


def test_geometry_summary_has_windings(
    context: tools.ToolContext, document: dict[str, object], tmp_path: Path
) -> None:
    target = tmp_path / "saved.inductor.json"
    _save(context, document, target)
    result = tools.geometry_summary(context, str(target))
    assert len(result["windings"]) == 2  # type: ignore[arg-type]


def test_generate_maxwell3d_returns_manifest_and_writes_evidence(
    context: tools.ToolContext, document: dict[str, object], tmp_path: Path
) -> None:
    target = tmp_path / "saved.inductor.json"
    _save(context, document, target)
    result = tools.generate_maxwell3d(context, str(target))
    assert result["backend"] == "aedt"
    assert result["succeeded"] is True
    evidence = context.output_root / "M2_golden_sample" / "generation-manifest.json"
    assert evidence.is_file()
    assert json.loads(evidence.read_text(encoding="utf-8")) == result


def test_generate_2d_femm_backend_has_results(
    context: tools.ToolContext, document_2d: dict[str, object], tmp_path: Path
) -> None:
    target = tmp_path / "saved.inductor.json"
    _save(context, document_2d, target)
    result = tools.generate_2d(context, str(target), backend="femm")
    assert result["backend"] == "femm"
    assert result["femmResults"] is not None
    evidence = context.output_root / "M2_golden_sample" / "femm-manifest.json"
    assert evidence.is_file()
    assert json.loads(evidence.read_text(encoding="utf-8")) == result


def test_generate_2d_femm_solver_raising_returns_error_dict(
    context: tools.ToolContext, document_2d: dict[str, object], tmp_path: Path
) -> None:
    class _RaisingFemmSolver:
        def solve(self, request: object) -> object:
            raise RuntimeError("Circuit 'primary' returned zero current")

    broken_context = tools.ToolContext(
        catalog=context.catalog,
        schemas=context.schemas,
        matrix_path=context.matrix_path,
        output_root=context.output_root,
        maxwell3d_exporter=context.maxwell3d_exporter,
        maxwell2d_exporter=context.maxwell2d_exporter,
        femm_solver=_RaisingFemmSolver(),  # type: ignore[arg-type]
    )
    target = tmp_path / "saved.inductor.json"
    _save(broken_context, document_2d, target)
    result = tools.generate_2d(broken_context, str(target), backend="femm")
    assert "error" in result


def test_generate_2d_bogus_backend_returns_error(
    context: tools.ToolContext, document_2d: dict[str, object], tmp_path: Path
) -> None:
    target = tmp_path / "saved.inductor.json"
    _save(context, document_2d, target)
    result = tools.generate_2d(context, str(target), backend="bogus")
    assert "error" in result


def test_read_manifest_roundtrip(
    context: tools.ToolContext, document: dict[str, object], tmp_path: Path
) -> None:
    target = tmp_path / "saved.inductor.json"
    _save(context, document, target)
    generated = tools.generate_maxwell3d(context, str(target))
    result = tools.read_manifest(context, "M2_golden_sample/generation-manifest.json")
    assert result == generated


def test_read_manifest_traversal_attack_returns_error(context: tools.ToolContext) -> None:
    result = tools.read_manifest(context, "../../etc/passwd")
    assert "error" in result
