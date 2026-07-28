# MCP server and FEMM 2D backend automation

Milestone 4.5 exposes the designer over MCP for AI-driven sessions and adds
FEMM as a user-selectable alternative to Ansys Maxwell for the 2D equivalent
model, including an in-loop solve with R/L result extraction.

> **Current planning status (2026-07-28):** The implemented nine-tool MCP
> surface is retained, but no MCP expansion, parity, or external-client
> validation belongs to M5a–M11. FEMM remains an active Windows-application
> backend. Future MCP work requires a separately approved scope after the
> Guided Studio and normalized result workflow are stable. M6 moved the
> existing generation tools to backend-independent Project schema v5, shared
> Run Requests, and shared Run Manifests without adding tools.

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
| `generate_maxwell3d` | Submit a Maxwell 3D Generate Only Run Request and return its Run Manifest. |
| `generate_2d` | Submit a Maxwell 2D or FEMM Run Request and return its Run Manifest. |
| `read_manifest` | Read back a previously written manifest JSON file from the output root. |

`generate_2d` takes `backend` (`"aedt"` or `"femm"`, default `"aedt"`) and the
retained `analyze` compatibility argument. Maxwell 2D always maps to Generate
Only. For FEMM, pass `analyze: false` for the implemented Generate Only request;
`analyze: true` maps to Generate and Solve and returns the explicit M8
not-implemented block before an adapter call. All tools return JSON-able dicts;
errors come back as `{"error": ..., "issues": [...]}` rather than raising, so
an MCP client always gets a structured result. Successful and failed adapter
executions write `run-manifest.json`.

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

The CLI and MCP choose the backend per call from the same backend-independent
schema-v5 Project document. Each entry point constructs a Run Request; no
backend or dimensional representation is persisted in the Project document.

CLI:

```powershell
.venv\Scripts\python.exe -m tools.generate_maxwell2d --project my.inductor.json --output-directory artifacts\out --evidence artifacts\out\evidence.json --backend femm
```

`--backend` defaults to `aedt`. The M6 CLI always submits Generate Only; solver
execution and result extraction belong to M8.

MCP:

```json
{"tool": "generate_2d", "arguments": {"path": "my.inductor.json", "backend": "femm", "analyze": false}}
```

Guided Studio: the Simulation section's backend dropdown lists "Maxwell 3D",
"Maxwell 2D (Ansys)", and "FEMM 2D"; the Generate button runs the selected
backend off the UI thread and streams stage/result lines into the panel.

## Verified behavior and limits

- **Circuit phase is applied at the FEMM adapter boundary.** Solver-independent
  planning supplies the already-converted AC peak magnitude and stored phase.
  The adapter converts that polar pair to the complex current accepted by
  `mi_addcircprop`; it performs no RMS-to-peak conversion. The M6 acceptance
  test proves that `2.8284271247461903 A peak` at `30°` reaches FEMM as
  approximately `2.449489742783178 + 1.414213562373095j A`.
- **Normalized loss and field-result extraction is M8 work.** M5 implemented
  pinned nonlinear material transfer for Maxwell and FEMM, but it did not add
  the normalized result contract or loss integrals.
- **Bore-interior air region lesson:** the core bore interior (`r <
  r_inner`) needs its own air block label at the origin — FEMM analysis
  otherwise fails with "Material properties have not been defined for all
  regions" because the outside-air label alone does not cover the enclosed
  bore. Fixed in commit `f30e662`; both air regions (bore interior and
  outside the core) now carry a label.

## Result sanity

Live run on FEMM 4.2 (2026-07-17), using the historical pre-M6 FEMM 2D CLI path
on the sample fixture
(`tests/fixtures/sample_geometry_project.inductor.json`) —
`artifacts/femm-check/M2_golden_sample_2d.fem`, all stages green:

- Winding `w1`: R ≈ 0.00854 Ω, L ≈ 15.16 µH at 100 kHz.
- Winding `w2`: R ≈ 0.00854 Ω, L ≈ 15.16 µH at 100 kHz.
- Both windings symmetric, as expected for the sample project's symmetric
  geometry.

These numbers are a smoke-test sanity check (nonzero, symmetric, right order
of magnitude), not an engineering acceptance figure. Milestone 4.5 is accepted;
traceable cross-backend comparison belongs to the M8 normalized-results
validation rather than retroactively gating M4.5.
