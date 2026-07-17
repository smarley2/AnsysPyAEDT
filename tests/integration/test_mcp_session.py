"""Integration test: MCP session flow with pure tools and recording fakes.

Scripted AI-session flow against the pure tools, no MCP transport.
Tests the complete design/generation/solve workflow.
"""

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

ROOT = Path(__file__).resolve().parents[2]
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


def test_mcp_session_end_to_end(
    context: tools.ToolContext,
    document: dict[str, object],
    document_2d: dict[str, object],
    tmp_path: Path,
) -> None:
    """Complete MCP session: design context, generation, FEMM solve, evidence read.

    Exit criterion for Milestone 4.5: a full workflow from core selection through
    2D/FEMM analysis without human/AEDT interaction.
    """
    # Step 1: list_cores → contains part 0077071A7
    list_result = tools.list_cores(context)
    assert "error" not in list_result
    part_numbers = [core["partNumber"] for core in list_result["cores"]]  # type: ignore[union-attr]
    assert "0077071A7" in part_numbers

    # Step 2: save_project → path + projectId returned
    project_path = tmp_path / "session.inductor.json"
    save_result = tools.save_project(context, document, str(project_path))
    assert "error" not in save_result
    assert save_result["path"] == str(project_path)
    assert save_result["projectId"] == document["projectId"]
    assert project_path.is_file()

    # Step 3: validate_project → no ERROR-category issues
    validate_result = tools.validate_project(context, str(project_path))
    assert "error" not in validate_result
    issues = validate_result["issues"]  # type: ignore[assignment]
    assert isinstance(issues, list)
    assert issues == []

    # Step 4: geometry_summary → windings present with turn data (layers)
    summary_result = tools.geometry_summary(context, str(project_path))
    assert "error" not in summary_result
    windings = summary_result["windings"]  # type: ignore[assignment]
    assert len(windings) == 2
    w1 = next((w for w in windings if w["windingId"] == "w1"), None)
    w2 = next((w for w in windings if w["windingId"] == "w2"), None)
    assert w1 is not None
    assert w2 is not None
    assert len(w1["layers"]) > 0  # Winding has layer data
    assert len(w2["layers"]) > 0  # Winding has layer data

    # Step 5: generate_maxwell3d → succeeded, dcBias.strategy, backend
    maxwell3d_result = tools.generate_maxwell3d(context, str(project_path))
    assert "error" not in maxwell3d_result
    assert maxwell3d_result["succeeded"] is True
    assert maxwell3d_result["backend"] == "aedt"
    dc_bias = maxwell3d_result.get("dcBias")  # type: ignore[assignment]
    assert dc_bias is not None
    assert dc_bias["strategy"] == "native-include-dc-fields"

    # Step 6: generate_2d with femm backend and analyze=True (needs 2d project)
    project_2d_path = tmp_path / "session_2d.inductor.json"
    tools.save_project(context, document_2d, str(project_2d_path))
    maxwell2d_result = tools.generate_2d(
        context, str(project_2d_path), backend="femm", analyze=True
    )
    assert "error" not in maxwell2d_result
    assert maxwell2d_result["backend"] == "femm"
    femm_results = maxwell2d_result.get("femmResults")  # type: ignore[assignment]
    assert femm_results is not None
    assert "w1" in femm_results
    assert "w2" in femm_results
    assert femm_results["w1"]["resistanceOhm"] > 0
    assert femm_results["w1"]["inductanceH"] > 0
    assert femm_results["w2"]["resistanceOhm"] > 0
    assert femm_results["w2"]["inductanceH"] > 0

    # Step 7: read_manifest on the femm evidence path
    evidence_path = "M2_golden_sample/femm-manifest.json"
    manifest_result = tools.read_manifest(context, evidence_path)
    assert "error" not in manifest_result
    assert manifest_result == maxwell2d_result
