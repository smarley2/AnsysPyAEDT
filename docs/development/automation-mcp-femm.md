# MCP server and FEMM 2D backend automation

Milestone 4.5 exposes the designer over MCP for AI-driven sessions and adds
FEMM as a user-selectable alternative to Ansys Maxwell for the 2D equivalent
model, including an in-loop solve with R/L result extraction.

> **Current planning status (2026-07-24):** The implemented nine-tool MCP
> surface is retained, but no MCP expansion, parity, or external-client
> validation belongs to M5a–M11. FEMM remains an active Windows-application
> backend. Future MCP work requires a separately approved scope after the
> Guided Studio and normalized result workflow are stable.

## MCP server

### Prerequisites

- `pip install -e ".[dev,mcp]"` (the `mcp` extra pulls the `mcp` Python SDK;
  it is also included in `dev` so CI can import the server module).
- The catalog index must already be built — the server never builds it
  itself:

  ```powershell
  python -m tools.build_catalog --source catalog --schemas schemas/catalog --out artifacts/catalog/catalog.sqlite
  ```

### Client configuration

`inductor-designer-mcp` is a console-script entry point that runs the server
over stdio. Example client config (Claude Desktop / any MCP stdio client):

```json
{
  "mcpServers": {
    "inductor-designer": {
      "command": "inductor-designer-mcp",
      "args": [
        "--root", "C:\\Work\\git\\AnsysPyAEDT",
        "--catalog-index", "C:\\Work\\git\\AnsysPyAEDT\\artifacts\\catalog\\catalog.sqlite"
      ]
    }
  }
}
```

`--root` defaults to the current working directory; `--catalog-index`
defaults to `<root>/artifacts/catalog/catalog.sqlite`. If the index is
missing, the server exits with a message naming the exact `build_catalog`
command to run.

### Tools

The server registers nine tools (`src/inductor_designer/mcp_server/server.py`
docstrings are the source of truth for wording):

| Tool | Description |
|---|---|
| `list_cores` | List every catalog core with its part number, material, and review status. |
| `get_core` | Fetch the full catalog record for one core by part number. |
| `list_conductors` | List every conductor name available in the catalog. |
| `save_project` | Validate an inductor project document and write it to the given file path. |
| `validate_project` | Load a saved project from disk and report its domain validation issues. |
| `geometry_summary` | Build the geometry model for a saved project and return its manifest summary. |
| `generate_maxwell3d` | Export a saved project to Maxwell 3D and return the generation manifest. |
| `generate_2d` | Export a saved project to a 2D AEDT or FEMM model and return its manifest. |
| `read_manifest` | Read back a previously written manifest JSON file from the output root. |

`generate_2d` takes `backend` (`"aedt"` or `"femm"`, default `"aedt"`) and
`analyze` (default `True`; FEMM only — `False` writes the `.fem` file without
running the analysis). All tools return JSON-able dicts; errors come back as
`{"error": ..., "issues": [...]}` rather than raising, so an MCP client always
gets a structured result.

## FEMM 2D backend

### Installation

1. Install FEMM 4.2 from [femm.info](https://www.femm.info) (freeware,
   Aladdin license — user-installed, never bundled with this project).
2. `pip install -e ".[femm]"` to add the `pyfemm` binding.
3. Live FEMM-touching tests are gated behind an environment variable so they
   never run by accident on a machine without FEMM installed:

   ```powershell
   $env:INDUCTOR_FEMM_LIVE = "1"
   .venv\Scripts\python.exe -m pytest tests/integration/femm -m femm
   ```

   The test skips unless both `pyfemm` imports successfully **and**
   `INDUCTOR_FEMM_LIVE=1` is set.

### Backend selection

Project files are backend-agnostic; the backend is chosen per call.

CLI:

```powershell
.venv\Scripts\python.exe -m tools.generate_maxwell2d --project my.inductor.json --output-directory artifacts\out --evidence artifacts\out\evidence.json --backend femm
```

(`--backend` defaults to `aedt`; add `--no-analyze` to write the `.fem` file
without solving.)

MCP:

```json
{"tool": "generate_2d", "arguments": {"path": "my.inductor.json", "backend": "femm", "analyze": true}}
```

Guided Studio: the Simulation section's backend dropdown lists "Maxwell 3D",
"Maxwell 2D (Ansys)", and "FEMM 2D"; the Generate button runs the selected
backend off the UI thread and streams stage/result lines into the panel.

## Verified limits (as of live verification, 2026-07-17)

- **Circuit phase is not applied to FEMM circuits yet.** FEMM circuits carry
  magnitude only; when a circuit's phase is nonzero, the adapter emits a
  message noting the phase was not applied rather than silently dropping it.
  Multi-phase FEMM excitation is deferred.
- **Loss integrals are deferred to Milestone 5**, alongside nonlinear
  material data for both backends.
- **Bore-interior air region lesson:** the core bore interior (`r <
  r_inner`) needs its own air block label at the origin — FEMM analysis
  otherwise fails with "Material properties have not been defined for all
  regions" because the outside-air label alone does not cover the enclosed
  bore. Fixed in commit `f30e662`; both air regions (bore interior and
  outside the core) now carry a label.

## Result sanity

Live run on FEMM 4.2 (2026-07-17), CLI: `python -m tools.generate_maxwell2d
--backend femm --force-2d` on the sample fixture
(`tests/fixtures/sample_geometry_project.inductor.json`) —
`artifacts/femm-check/M2_golden_sample_2d.fem`, all stages green:

- Winding `w1`: R ≈ 0.00854 Ω, L ≈ 15.16 µH at 100 kHz.
- Winding `w2`: R ≈ 0.00854 Ω, L ≈ 15.16 µH at 100 kHz.
- Both windings symmetric, as expected for the sample project's symmetric
  geometry.

These numbers are a smoke-test sanity check (nonzero, symmetric, right order
of magnitude), not an engineering acceptance figure — comparing them against
an equivalent AEDT 2D or 3D solve is part of Milestone 4.5 acceptance.
