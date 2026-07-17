from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from inductor_designer.adapters.catalog.sqlite_repository import SqliteCatalogRepository
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from inductor_designer.mcp_server import tools
from inductor_designer.mcp_server.server import create_server
from tests.fakes.femm_solver import RecordingFemmSolver
from tests.fakes.maxwell2d_exporter import RecordingMaxwell2dExporter
from tests.fakes.maxwell_exporter import RecordingMaxwell3dExporter

ROOT = Path(__file__).resolve().parents[3]

EXPECTED_TOOL_NAMES = {
    "list_cores",
    "get_core",
    "list_conductors",
    "save_project",
    "validate_project",
    "geometry_summary",
    "generate_maxwell3d",
    "generate_2d",
    "read_manifest",
}


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


def test_create_server_registers_exactly_the_nine_tools(context: tools.ToolContext) -> None:
    server = create_server(context)
    registered = asyncio.run(server.list_tools())
    assert {tool.name for tool in registered} == EXPECTED_TOOL_NAMES


def test_call_tool_list_cores_returns_catalog_part_number(context: tools.ToolContext) -> None:
    server = create_server(context)
    # FastMCP.call_tool returns (content_blocks, structured_result_dict).
    _content, structured = asyncio.run(server.call_tool("list_cores", {}))
    assert isinstance(structured, dict)
    part_numbers = [core["partNumber"] for core in structured["cores"]]  # type: ignore[index]
    assert "0077071A7" in part_numbers
