"""FastMCP stdio server exposing the nine :mod:`tools` functions.

``build_context`` wires real adapters (SQLite catalog, PyAEDT/FEMM exporters)
onto a :class:`~inductor_designer.mcp_server.tools.ToolContext`. It never
builds the catalog itself: ``--catalog-index`` must already exist (build it
with ``python -m tools.build_catalog``, whose documented default output is
``artifacts/catalog/catalog.sqlite`` under the repo root) so this module
never imports the dev-only ``tools`` package.

``create_server`` registers each tool function as a closure bound to a
``ToolContext`` and returns a ``FastMCP`` instance; ``main`` is the
``inductor-designer-mcp`` console-script entry point, running the server
over stdio.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from inductor_designer.adapters.catalog.sqlite_repository import SqliteCatalogRepository
from inductor_designer.adapters.femm.solver import PyfemmSolver
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from inductor_designer.adapters.pyaedt.maxwell2d import PyaedtMaxwell2dExporter
from inductor_designer.adapters.pyaedt.maxwell3d import PyaedtMaxwell3dExporter
from inductor_designer.mcp_server import tools
from inductor_designer.mcp_server.tools import ToolContext

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

DEFAULT_CATALOG_INDEX = Path("artifacts") / "catalog" / "catalog.sqlite"


def build_context(root: Path, catalog_index: Path | None = None) -> ToolContext:
    """Wire a :class:`ToolContext` from an already-built catalog index."""
    index = catalog_index if catalog_index is not None else root / DEFAULT_CATALOG_INDEX
    if not index.is_file():
        raise FileNotFoundError(
            f"Catalog index not found: {index}. Build it with "
            "'python -m tools.build_catalog --source "
            f"{root / 'catalog'} --schemas {root / 'schemas' / 'catalog'} --out {index}'."
        )
    return ToolContext(
        catalog=SqliteCatalogRepository(index),
        schemas=SchemaRepository(root / "schemas"),
        matrix_path=root / "compatibility" / "aedt-matrix.yml",
        output_root=root / "artifacts" / "mcp",
        maxwell3d_exporter=PyaedtMaxwell3dExporter(),
        maxwell2d_exporter=PyaedtMaxwell2dExporter(),
        femm_solver=PyfemmSolver(),
    )


def create_server(context: ToolContext) -> FastMCP:
    """Build a FastMCP server exposing the nine inductor-designer tools."""
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("inductor-designer")

    def list_cores() -> dict[str, object]:
        """List every catalog core with its part number, material, and review status."""
        return tools.list_cores(context)

    def get_core(part_number: str) -> dict[str, object]:
        """Fetch the full catalog record for one core by part number."""
        return tools.get_core(context, part_number)

    def list_conductors() -> dict[str, object]:
        """List every conductor name available in the catalog."""
        return tools.list_conductors(context)

    def save_project(document: Mapping[str, object], path: str) -> dict[str, object]:
        """Validate an inductor project document and write it to the given file path."""
        return tools.save_project(context, document, path)

    def validate_project(path: str) -> dict[str, object]:
        """Load a saved project from disk and report its domain validation issues."""
        return tools.validate_project(context, path)

    def geometry_summary(path: str) -> dict[str, object]:
        """Build the geometry model for a saved project and return its manifest summary."""
        return tools.geometry_summary(context, path)

    def generate_maxwell3d(path: str) -> dict[str, object]:
        """Export a saved project to Maxwell 3D and return the generation manifest."""
        return tools.generate_maxwell3d(context, path)

    def generate_2d(path: str, backend: str = "aedt", analyze: bool = True) -> dict[str, object]:
        """Export a saved project to a 2D AEDT or FEMM model and return its manifest."""
        return tools.generate_2d(context, path, backend=backend, analyze=analyze)

    def read_manifest(path: str) -> dict[str, object]:
        """Read back a previously written manifest JSON file from the output root."""
        return tools.read_manifest(context, path)

    for tool_fn in (
        list_cores,
        get_core,
        list_conductors,
        save_project,
        validate_project,
        geometry_summary,
        generate_maxwell3d,
        generate_2d,
        read_manifest,
    ):
        server.add_tool(tool_fn)

    return server


def main(argv: Sequence[str] | None = None) -> int:
    """Console-script entry point: run the stdio MCP server."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--catalog-index", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        context = build_context(args.root, args.catalog_index)
    except FileNotFoundError as error:
        parser.error(str(error))
        return 2  # pragma: no cover - argparse.error() exits before returning

    create_server(context).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
