# M8b Scalar Normalized Results Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn a solved run into a Normalized Result Set of scalar quantities — resistance, inductance, impedance, supported matrices, copper/core/total loss, magnetic energy, convergence and solver status — export it as JSON and CSV beside the run, and show it on the Review screen.

**Architecture:** M8a already solves and leaves a truthful manifest. M8b adds one extraction step after the `analyze` stage: each adapter returns backend-raw values through a narrow protocol, one pure service normalizes them into the existing `NormalizedQuantity` contract, `start_project_run` puts the result set into the manifest and writes `results.json` and `results.csv` into the run's `results/` directory, and the Review screen renders them beside the M7a analytical estimates. No field quantity is touched: `flux-density` and `current-density` stay out until M8c.

**Tech Stack:** Python 3.13, PySide6/QML, PyAEDT against AEDT 2025 R2 Commercial, pyFEMM against FEMM 4.2, pytest with `pytest-xdist`, Ruff, strict mypy.

## Global Constraints

- The only supported AEDT target is AEDT 2025 R2 Commercial.
- `domain`, `geometry`, `materials` and `simulation` import no PyAEDT, no Qt, no SQLite and no operating-system API; `tools/check_architecture.py` enforces this.
- Never change a physical assumption, schema, catalog value, unit, source reference or approximation silently.
- Add or update tests before implementing a feature or a fix.
- A quantity that cannot be obtained without misrepresentation is `unavailable` with a reason. It is never silently estimated or omitted (roadmap realignment section 8).
- Diagnostic and reason codes are lowercase dotted `<quantity>.<reason>` strings.
- The project current is RMS; the solver excitation is peak (ADR 0006). Every reported quantity states its `current_convention`.
- All code, comments, commits and UI copy in English.
- Full suite: `.venv/Scripts/python.exe -m pytest -n 8`. Live suites are behind the `aedt` and `femm` markers.

## Decisions taken with Fabio Posser on 2026-08-10

1. **Export is automatic.** Every solve run writes `results.json` and `results.csv` into its own `runs/<run-id>-<backend>/results/`, beside `solve-log.txt`. There is no export button and no chosen path; the run directory is self-contained evidence.
2. **Results are a Review section.** They become another section on the existing Review screen, beside core, windings, preliminary and run. The approved five-screen Guided Studio flow does not change, and the FEM numbers sit next to the M7a analytical estimates.
3. **A derived total loss is allowed, labelled.** When a backend reports copper loss and core loss but no total, total loss is reported as their sum with `approximation` naming it a sum of the two reported parts and `provenance` saying `derived`. It is never presented as a solver-reported value.

## Scope

In scope: per-winding resistance, inductance and complex impedance; resistance and inductance matrices where the backend exposes them without reinterpretation; copper, core and total loss; magnetic energy; convergence history with the final state; solver status and diagnostics; JSON and CSV export; the Review results section.

Out of scope: every field quantity — `flux-density` and `current-density`, representative cross sections, area-weighted means — which is M8c and specified in the [2026-08-10 Representative Cross Sections design](../specs/2026-08-10-representative-cross-sections-design.md).

## File Structure

| File | Responsibility |
| --- | --- |
| `src/inductor_designer/simulation/result_vocabulary.py` (create) | Pure: unit, scope and current convention per scalar quantity; reason codes |
| `src/inductor_designer/simulation/result_expressions.py` (create) | Pure: the backend expression strings Maxwell is asked for, in one table |
| `src/inductor_designer/simulation/raw_results.py` (create) | Pure: the backend-neutral raw value structure both adapters return |
| `src/inductor_designer/application/services/result_normalization.py` (create) | Raw values into `NormalizedResultSet`, with availability and the labelled derivation |
| `src/inductor_designer/application/services/result_export.py` (create) | `results.json` and `results.csv` writers |
| `src/inductor_designer/application/ports/maxwell_exporter.py` (modify) | `RawScalarResults` on the export result |
| `src/inductor_designer/application/ports/maxwell2d_exporter.py` (modify) | Same, for 2D |
| `src/inductor_designer/adapters/pyaedt/maxwell3d.py` (modify) | `results` stage: read solution data and convergence |
| `src/inductor_designer/adapters/pyaedt/maxwell2d.py` (modify) | Same, for 2D |
| `src/inductor_designer/adapters/pyaedt/result_reader.py` (create) | The PyAEDT calls behind the extraction, shared by both Maxwell adapters |
| `src/inductor_designer/adapters/femm/solver.py` (modify) | Return the same raw structure from the circuit quantities it already extracts |
| `src/inductor_designer/application/services/maxwell_export.py` (modify) | Normalize into `RunManifest.results` |
| `src/inductor_designer/application/services/project_run.py` (modify) | Write the two export files for a solve run |
| `src/inductor_designer/ui/review_controller.py` (modify) | The results section rows |
| `src/inductor_designer/ui/qml/ReviewPage.qml` (modify) | Render the results section |

---

### Task 1: Scalar result vocabulary

**Files:**
- Create: `src/inductor_designer/simulation/result_vocabulary.py`
- Test: `tests/unit/simulation/test_result_vocabulary.py`

**Interfaces:**
- Consumes: `RequestedOutput`, `CurrentConvention` from the existing contracts.
- Produces: `SCALAR_QUANTITIES: tuple[RequestedOutput, ...]` (everything except `FLUX_DENSITY` and `CURRENT_DENSITY`); `unit_for(quantity) -> str`; `convention_for(quantity) -> CurrentConvention`; `winding_scope(winding_id) -> str` returning `winding.<id>`; `DEVICE_SCOPE = "device"`; reason-code constants `NOT_EXPOSED`, `NOT_REPORTED`, `NOT_SOLVED`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/simulation/test_result_vocabulary.py
from inductor_designer.domain.project import RequestedOutput
from inductor_designer.simulation.result_contracts import CurrentConvention
from inductor_designer.simulation.result_vocabulary import (
    DEVICE_SCOPE,
    SCALAR_QUANTITIES,
    convention_for,
    reason_code,
    unit_for,
    winding_scope,
)


def test_field_quantities_are_not_scalar_work() -> None:
    assert RequestedOutput.FLUX_DENSITY not in SCALAR_QUANTITIES
    assert RequestedOutput.CURRENT_DENSITY not in SCALAR_QUANTITIES
    assert RequestedOutput.RESISTANCE in SCALAR_QUANTITIES


def test_every_scalar_quantity_has_a_unit_and_a_convention() -> None:
    for quantity in SCALAR_QUANTITIES:
        assert unit_for(quantity).strip()
        assert isinstance(convention_for(quantity), CurrentConvention)


def test_units_are_si_and_exact() -> None:
    assert unit_for(RequestedOutput.RESISTANCE) == "ohm"
    assert unit_for(RequestedOutput.INDUCTANCE) == "H"
    assert unit_for(RequestedOutput.IMPEDANCE) == "ohm"
    assert unit_for(RequestedOutput.COPPER_LOSS) == "W"
    assert unit_for(RequestedOutput.CORE_LOSS) == "W"
    assert unit_for(RequestedOutput.TOTAL_LOSS) == "W"
    assert unit_for(RequestedOutput.MAGNETIC_ENERGY) == "J"
    assert unit_for(RequestedOutput.CONVERGENCE) == "percent"


def test_losses_and_energy_are_reported_at_ac_rms() -> None:
    """A loss is a mean power over the cycle, so it is an RMS-convention value."""
    assert convention_for(RequestedOutput.COPPER_LOSS) is CurrentConvention.AC_RMS
    assert convention_for(RequestedOutput.CORE_LOSS) is CurrentConvention.AC_RMS
    assert convention_for(RequestedOutput.MAGNETIC_ENERGY) is CurrentConvention.AC_PEAK


def test_convergence_is_convention_free() -> None:
    assert convention_for(RequestedOutput.CONVERGENCE) is CurrentConvention.NOT_APPLICABLE


def test_scopes_and_reason_codes_are_stable_strings() -> None:
    assert winding_scope("w1") == "winding.w1"
    assert DEVICE_SCOPE == "device"
    assert reason_code(RequestedOutput.MATRICES, "not_exposed") == "matrices.not_exposed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/simulation/test_result_vocabulary.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'inductor_designer.simulation.result_vocabulary'`

- [ ] **Step 3: Write the implementation**

```python
# src/inductor_designer/simulation/result_vocabulary.py
"""Units, scopes and conventions for the scalar Normalized Result Set.

One table, so a unit or a convention is never decided at a call site. Field
quantities are absent on purpose: they are M8c.
"""

from __future__ import annotations

from inductor_designer.domain.project import RequestedOutput
from inductor_designer.simulation.run_contracts import CurrentConvention

DEVICE_SCOPE = "device"

SCALAR_QUANTITIES: tuple[RequestedOutput, ...] = (
    RequestedOutput.RESISTANCE,
    RequestedOutput.INDUCTANCE,
    RequestedOutput.IMPEDANCE,
    RequestedOutput.MATRICES,
    RequestedOutput.COPPER_LOSS,
    RequestedOutput.CORE_LOSS,
    RequestedOutput.TOTAL_LOSS,
    RequestedOutput.MAGNETIC_ENERGY,
    RequestedOutput.CONVERGENCE,
)

_UNITS: dict[RequestedOutput, str] = {
    RequestedOutput.RESISTANCE: "ohm",
    RequestedOutput.INDUCTANCE: "H",
    RequestedOutput.IMPEDANCE: "ohm",
    RequestedOutput.MATRICES: "ohm and H",
    RequestedOutput.COPPER_LOSS: "W",
    RequestedOutput.CORE_LOSS: "W",
    RequestedOutput.TOTAL_LOSS: "W",
    RequestedOutput.MAGNETIC_ENERGY: "J",
    RequestedOutput.CONVERGENCE: "percent",
}

# A loss is the mean power over one cycle, so it belongs to the RMS current
# convention even though the solver is excited at peak (ADR 0006). Stored
# magnetic energy is an instantaneous peak-excitation quantity.
_CONVENTIONS: dict[RequestedOutput, CurrentConvention] = {
    RequestedOutput.RESISTANCE: CurrentConvention.NOT_APPLICABLE,
    RequestedOutput.INDUCTANCE: CurrentConvention.NOT_APPLICABLE,
    RequestedOutput.IMPEDANCE: CurrentConvention.NOT_APPLICABLE,
    RequestedOutput.MATRICES: CurrentConvention.NOT_APPLICABLE,
    RequestedOutput.COPPER_LOSS: CurrentConvention.AC_RMS,
    RequestedOutput.CORE_LOSS: CurrentConvention.AC_RMS,
    RequestedOutput.TOTAL_LOSS: CurrentConvention.AC_RMS,
    RequestedOutput.MAGNETIC_ENERGY: CurrentConvention.AC_PEAK,
    RequestedOutput.CONVERGENCE: CurrentConvention.NOT_APPLICABLE,
}

NOT_EXPOSED = "not_exposed"
NOT_REPORTED = "not_reported"
NOT_SOLVED = "not_solved"


def unit_for(quantity: RequestedOutput) -> str:
    return _UNITS[quantity]


def convention_for(quantity: RequestedOutput) -> CurrentConvention:
    return _CONVENTIONS[quantity]


def winding_scope(winding_id: str) -> str:
    return f"winding.{winding_id}"


def reason_code(quantity: RequestedOutput, reason: str) -> str:
    return f"{quantity.value}.{reason}"
```

Note the test imports `CurrentConvention` from `result_contracts`; it lives in `run_contracts`. Fix the test import to `inductor_designer.simulation.run_contracts` before running.

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/simulation -q && .venv/Scripts/python.exe -m tools.check_architecture`
Expected: PASS, then a clean architecture check

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/simulation/result_vocabulary.py tests/unit/simulation/test_result_vocabulary.py
git commit -m "feat(simulation): add the scalar result vocabulary"
```

---

### Task 2: The backend-neutral raw result structure

**Files:**
- Create: `src/inductor_designer/simulation/raw_results.py`
- Test: `tests/unit/simulation/test_raw_results.py`

**Interfaces:**
- Consumes: nothing outside the standard library and the existing contracts.
- Produces: `RawWindingResult(winding_id: str, resistance_ohm: float | None, inductance_h: float | None, impedance: complex | None)`; `RawMatrix(kind: str, labels: tuple[str, ...], values: tuple[tuple[float, ...], ...])`; `RawConvergence(passes: tuple[tuple[int, float], ...], converged: bool | None)`; `RawScalarResults(windings, matrices, copper_loss_w, core_loss_w, total_loss_w, magnetic_energy_j, convergence, solver_status, diagnostics)`; every scalar field is `X | None`, where `None` means the backend did not report it.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/simulation/test_raw_results.py
import pytest

from inductor_designer.simulation.raw_results import (
    RawConvergence,
    RawMatrix,
    RawScalarResults,
    RawWindingResult,
)


def test_an_empty_raw_result_reports_nothing_rather_than_zero() -> None:
    raw = RawScalarResults()
    assert raw.windings == ()
    assert raw.copper_loss_w is None
    assert raw.core_loss_w is None
    assert raw.total_loss_w is None
    assert raw.magnetic_energy_j is None
    assert raw.convergence is None
    assert raw.matrices == ()


def test_a_winding_result_keeps_partial_evidence() -> None:
    winding = RawWindingResult(winding_id="w1", resistance_ohm=0.1)
    assert winding.inductance_h is None
    assert winding.impedance is None


def test_a_matrix_must_be_square_against_its_labels() -> None:
    with pytest.raises(ValueError, match="square"):
        RawMatrix(kind="inductance", labels=("w1", "w2"), values=((1.0, 2.0),))


def test_convergence_rows_are_pass_and_error() -> None:
    convergence = RawConvergence(passes=((1, 12.5), (2, 0.8)), converged=True)
    assert convergence.passes[-1] == (2, 0.8)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/simulation/test_raw_results.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'inductor_designer.simulation.raw_results'`

- [ ] **Step 3: Write the implementation**

```python
# src/inductor_designer/simulation/raw_results.py
"""What a backend reported, before any normalization.

Every field is optional: ``None`` means the backend did not report the
quantity, which the normalizer turns into an explicit unavailable reason
rather than a zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class RawWindingResult:
    winding_id: str
    resistance_ohm: float | None = None
    inductance_h: float | None = None
    impedance: complex | None = None


@dataclass(frozen=True, slots=True)
class RawMatrix:
    kind: str
    labels: tuple[str, ...]
    values: tuple[tuple[float, ...], ...]

    def __post_init__(self) -> None:
        size = len(self.labels)
        if len(self.values) != size or any(len(row) != size for row in self.values):
            raise ValueError("a reported matrix must be square against its labels")


@dataclass(frozen=True, slots=True)
class RawConvergence:
    passes: tuple[tuple[int, float], ...]
    converged: bool | None = None


@dataclass(frozen=True, slots=True)
class RawScalarResults:
    windings: tuple[RawWindingResult, ...] = ()
    matrices: tuple[RawMatrix, ...] = ()
    copper_loss_w: float | None = None
    core_loss_w: float | None = None
    total_loss_w: float | None = None
    magnetic_energy_j: float | None = None
    convergence: RawConvergence | None = None
    solver_status: str | None = None
    diagnostics: tuple[str, ...] = field(default_factory=tuple)
```

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/simulation -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/simulation/raw_results.py tests/unit/simulation/test_raw_results.py
git commit -m "feat(simulation): add the backend-neutral raw scalar result structure"
```

---

### Task 3: Normalization

**Files:**
- Create: `src/inductor_designer/application/services/result_normalization.py`
- Test: `tests/unit/application/test_result_normalization.py`

**Interfaces:**
- Consumes: `RawScalarResults` (Task 2), the vocabulary (Task 1), `NormalizedQuantity`, `NormalizedResultSet`, `ComplexValue`, `MatrixValue`, `ResultAvailability`.
- Produces: `normalize_scalar_results(raw, *, run_id, backend, requested_outputs, provenance) -> NormalizedResultSet`. Every requested scalar quantity appears exactly once per scope, available or unavailable with a reason. `DERIVED_TOTAL_LOSS_NOTE` is the exact approximation string for a summed total.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/application/test_result_normalization.py
from inductor_designer.application.services.result_normalization import (
    DERIVED_TOTAL_LOSS_NOTE,
    normalize_scalar_results,
)
from inductor_designer.domain.project import RequestedOutput
from inductor_designer.simulation.raw_results import (
    RawConvergence,
    RawMatrix,
    RawScalarResults,
    RawWindingResult,
)
from inductor_designer.simulation.run_contracts import (
    ComplexValue,
    MatrixValue,
    ResultAvailability,
    RunBackend,
)

ALL = tuple(
    output
    for output in RequestedOutput
    if output
    not in (RequestedOutput.FLUX_DENSITY, RequestedOutput.CURRENT_DENSITY)
)


def normalize(raw: RawScalarResults, outputs=ALL):
    return normalize_scalar_results(
        raw,
        run_id="20260810-120000",
        backend=RunBackend.MAXWELL_3D,
        requested_outputs=outputs,
        provenance="Maxwell 3D solution data",
    )


def find(result_set, quantity, scope):
    return next(
        item
        for item in result_set.quantities
        if item.quantity is quantity and item.scope == scope
    )


def test_a_reported_resistance_is_available_with_unit_and_provenance() -> None:
    raw = RawScalarResults(
        windings=(RawWindingResult(winding_id="w1", resistance_ohm=0.125),)
    )

    entry = find(normalize(raw), RequestedOutput.RESISTANCE, "winding.w1")

    assert entry.availability is ResultAvailability.AVAILABLE
    assert entry.value == 0.125
    assert entry.unit == "ohm"
    assert entry.provenance == "Maxwell 3D solution data"
    assert entry.reason is None


def test_a_missing_quantity_is_unavailable_with_a_dotted_reason() -> None:
    raw = RawScalarResults(windings=(RawWindingResult(winding_id="w1"),))

    entry = find(normalize(raw), RequestedOutput.INDUCTANCE, "winding.w1")

    assert entry.availability is ResultAvailability.UNAVAILABLE
    assert entry.value is None
    assert entry.reason is not None
    assert entry.reason.startswith("inductance.not_reported")


def test_an_impedance_is_reported_as_a_complex_value() -> None:
    raw = RawScalarResults(
        windings=(RawWindingResult(winding_id="w1", impedance=complex(0.1, 3.2)),)
    )

    entry = find(normalize(raw), RequestedOutput.IMPEDANCE, "winding.w1")

    assert entry.value == ComplexValue(real=0.1, imaginary=3.2)


def test_a_reported_matrix_becomes_a_matrix_value() -> None:
    raw = RawScalarResults(
        matrices=(
            RawMatrix(
                kind="inductance",
                labels=("w1", "w2"),
                values=((1e-4, 2e-5), (2e-5, 9e-5)),
            ),
        )
    )

    entry = find(normalize(raw), RequestedOutput.MATRICES, "device.inductance")

    assert isinstance(entry.value, MatrixValue)
    assert entry.value.row_labels == ("w1", "w2")


def test_total_loss_is_derived_from_the_parts_and_says_so() -> None:
    raw = RawScalarResults(copper_loss_w=3.0, core_loss_w=1.25)

    entry = find(normalize(raw), RequestedOutput.TOTAL_LOSS, "device")

    assert entry.value == 4.25
    assert entry.approximation == DERIVED_TOTAL_LOSS_NOTE
    assert entry.provenance is not None
    assert "derived" in entry.provenance


def test_a_reported_total_loss_is_never_overwritten_by_the_sum() -> None:
    raw = RawScalarResults(copper_loss_w=3.0, core_loss_w=1.25, total_loss_w=4.4)

    entry = find(normalize(raw), RequestedOutput.TOTAL_LOSS, "device")

    assert entry.value == 4.4
    assert entry.approximation is None


def test_total_loss_is_unavailable_when_a_part_is_missing() -> None:
    raw = RawScalarResults(copper_loss_w=3.0)

    entry = find(normalize(raw), RequestedOutput.TOTAL_LOSS, "device")

    assert entry.availability is ResultAvailability.UNAVAILABLE
    assert entry.reason is not None and "core" in entry.reason


def test_convergence_reports_the_final_error_and_the_history() -> None:
    raw = RawScalarResults(
        convergence=RawConvergence(passes=((1, 12.5), (2, 0.8)), converged=True)
    )

    entry = find(normalize(raw), RequestedOutput.CONVERGENCE, "device")

    assert entry.value == 0.8
    assert entry.provenance is not None and "2 passes" in entry.provenance


def test_a_quantity_the_user_did_not_request_is_absent(
) -> None:
    raw = RawScalarResults(copper_loss_w=3.0)

    result_set = normalize(raw, outputs=(RequestedOutput.RESISTANCE,))

    assert all(
        item.quantity is RequestedOutput.RESISTANCE for item in result_set.quantities
    )


def test_normalization_never_invents_a_scope_without_a_winding() -> None:
    result_set = normalize(RawScalarResults())

    assert all(not item.scope.startswith("winding.") for item in result_set.quantities)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/application/test_result_normalization.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'inductor_designer.application.services.result_normalization'`

- [ ] **Step 3: Write the implementation**

Build one `NormalizedQuantity` per requested scalar quantity per scope. Per-winding quantities (`resistance`, `inductance`, `impedance`) iterate `raw.windings` and use `winding_scope`; device quantities (`losses`, `magnetic-energy`, `convergence`) use `DEVICE_SCOPE`; `matrices` uses `device.<kind>`. A `None` raw value becomes `unavailable` with `reason_code(quantity, NOT_REPORTED)` plus a sentence naming the backend. Total loss follows decision 3:

```python
DERIVED_TOTAL_LOSS_NOTE = (
    "Sum of the reported copper loss and core loss; the backend did not "
    "report a total."
)


def _total_loss(raw: RawScalarResults, provenance: str) -> NormalizedQuantity:
    if raw.total_loss_w is not None:
        return _available(
            RequestedOutput.TOTAL_LOSS, DEVICE_SCOPE, raw.total_loss_w, provenance
        )
    if raw.copper_loss_w is None or raw.core_loss_w is None:
        missing = "copper loss" if raw.copper_loss_w is None else "core loss"
        return _unavailable(
            RequestedOutput.TOTAL_LOSS,
            DEVICE_SCOPE,
            f"{reason_code(RequestedOutput.TOTAL_LOSS, NOT_REPORTED)}: the "
            f"backend reported neither a total loss nor a {missing} to sum.",
        )
    return _available(
        RequestedOutput.TOTAL_LOSS,
        DEVICE_SCOPE,
        raw.copper_loss_w + raw.core_loss_w,
        f"derived from {provenance}",
        approximation=DERIVED_TOTAL_LOSS_NOTE,
    )
```

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/application -q && .venv/Scripts/python.exe -m mypy src tools`
Expected: PASS, then `Success: no issues found`

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/application/services/result_normalization.py tests/unit/application/test_result_normalization.py
git commit -m "feat(simulation): normalize raw scalar results with explicit availability"
```

---

### Task 4: Maxwell extraction

**Files:**
- Create: `src/inductor_designer/simulation/result_expressions.py`
- Create: `src/inductor_designer/adapters/pyaedt/result_reader.py`
- Modify: `src/inductor_designer/adapters/pyaedt/maxwell3d.py`, `src/inductor_designer/adapters/pyaedt/maxwell2d.py`
- Modify: `src/inductor_designer/application/ports/maxwell_exporter.py` (add `raw_results: RawScalarResults | None = None` to `Maxwell3dExportResult`)
- Test: `tests/unit/simulation/test_result_expressions.py`, `tests/unit/adapters/test_maxwell_result_extraction.py`

**Interfaces:**
- Consumes: `RawScalarResults`, the winding names in the plan, the matrix name in the plan.
- Produces: pure `matrix_expressions(matrix_name, winding_names) -> tuple[str, ...]` and `DEVICE_EXPRESSIONS: tuple[str, ...]`; the `Maxwell3dApp`/`Maxwell2dApp` protocols gain `solution_values(expressions: tuple[str, ...]) -> Mapping[str, complex]` and `convergence_rows(setup_name: str) -> tuple[tuple[int, float], ...]`; the adapters run one `results` stage after `analyze` and attach `raw_results` to their export result. The `results` stage never fails a run: an extraction error is recorded as a diagnostic on `RawScalarResults.diagnostics`, and the affected quantities normalize to `unavailable`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/simulation/test_result_expressions.py
from inductor_designer.simulation.result_expressions import (
    DEVICE_EXPRESSIONS,
    matrix_expressions,
    parse_matrix_expression,
)


def test_matrix_expressions_cover_every_pair_once() -> None:
    expressions = matrix_expressions("Matrix1", ("w1", "w2"))

    assert "Matrix1.L(w1,w1)" in expressions
    assert "Matrix1.L(w1,w2)" in expressions
    assert "Matrix1.R(w2,w2)" in expressions
    assert len(expressions) == 2 * 2 * 2  # two kinds, two-by-two matrix


def test_an_expression_round_trips_back_to_its_meaning() -> None:
    assert parse_matrix_expression("Matrix1.L(w1,w2)") == ("inductance", "w1", "w2")
    assert parse_matrix_expression("Matrix1.R(w2,w1)") == ("resistance", "w2", "w1")
    assert parse_matrix_expression("SolidLoss") is None


def test_device_expressions_are_the_documented_maxwell_names() -> None:
    assert DEVICE_EXPRESSIONS == ("SolidLoss", "CoreLoss", "Total_Energy")
```

```python
# tests/unit/adapters/test_maxwell_result_extraction.py
from pathlib import Path

import pytest

from inductor_designer.adapters.pyaedt.maxwell3d import PyaedtMaxwell3dExporter
from inductor_designer.application.ports.maxwell_exporter import (
    SOLVE_STAGE_NAMES,
    Maxwell3dExportRequest,
)
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from tests.fakes.maxwell3d_app import FakeMaxwell3dApp, FakeMaxwell3dAppFactory
from tests.unit.simulation.test_plan_builder import build, make_definition

pytestmark = pytest.mark.usefixtures("fake_maxwell_boundary")


def export(tmp_path: Path, app: FakeMaxwell3dApp, **overrides: object):
    base: dict[str, object] = {
        "plan": build((make_definition(),)),
        "release": AedtRelease(2025, 2),
        "edition": AedtEdition.COMMERCIAL,
        "non_graphical": True,
        "output_directory": tmp_path / "out",
        "project_name": "Result_case",
        "solve": True,
    }
    base.update(overrides)
    return PyaedtMaxwell3dExporter(app_factory=FakeMaxwell3dAppFactory(app)).export(
        Maxwell3dExportRequest(**base)  # type: ignore[arg-type]
    )


def test_a_solved_run_attaches_raw_results(tmp_path: Path) -> None:
    result = export(tmp_path, FakeMaxwell3dApp())

    assert result.raw_results is not None
    assert result.raw_results.windings[0].winding_id == "w1"
    assert result.raw_results.copper_loss_w == pytest.approx(3.0)
    assert result.raw_results.convergence is not None


def test_a_generate_only_run_attaches_no_results(tmp_path: Path) -> None:
    result = export(tmp_path, FakeMaxwell3dApp(), solve=False)

    assert result.raw_results is None


def test_the_results_stage_appears_after_analyze(tmp_path: Path) -> None:
    result = export(tmp_path, FakeMaxwell3dApp())

    names = tuple(stage.name for stage in result.stages)
    assert names == SOLVE_STAGE_NAMES + ("results",)


def test_an_extraction_failure_never_fails_the_solved_run(tmp_path: Path) -> None:
    app = FakeMaxwell3dApp()
    app.fail_solution_values = True

    result = export(tmp_path, app)

    stage = [item for item in result.stages if item.name == "results"][0]
    assert stage.succeeded is True, "the solve itself succeeded"
    assert result.raw_results is not None
    assert result.raw_results.diagnostics, "the failure is recorded, not swallowed"
    assert result.raw_results.windings == ()
```

Extend `tests/fakes/maxwell3d_app.py` with `fail_solution_values: bool`, plus

```python
    def solution_values(self, expressions: tuple[str, ...]) -> dict[str, complex]:
        if self.fail_solution_values:
            raise RuntimeError("Solution data is not available for this setup.")
        values: dict[str, complex] = {"SolidLoss": 3.0 + 0j, "CoreLoss": 1.25 + 0j,
                                      "Total_Energy": 4.2e-4 + 0j}
        for expression in expressions:
            if expression.startswith("Matrix1.L("):
                values[expression] = 1e-4 + 0j
            elif expression.startswith("Matrix1.R("):
                values[expression] = 0.125 + 0j
        return values

    def convergence_rows(self, name: str) -> tuple[tuple[int, float], ...]:
        return ((1, 12.5), (2, 0.8))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/simulation/test_result_expressions.py tests/unit/adapters/test_maxwell_result_extraction.py -q`
Expected: FAIL on the missing module and the missing `results` stage

- [ ] **Step 3: Write the implementation**

`result_expressions.py` builds the expression strings and parses them back, so nothing outside it knows Maxwell's naming:

```python
MATRIX_KINDS = {"L": "inductance", "R": "resistance"}
DEVICE_EXPRESSIONS: tuple[str, ...] = ("SolidLoss", "CoreLoss", "Total_Energy")


def matrix_expressions(matrix_name: str, winding_names: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        f"{matrix_name}.{symbol}({row},{column})"
        for symbol in MATRIX_KINDS
        for row in winding_names
        for column in winding_names
    )
```

`result_reader.py` turns one app plus one plan into a `RawScalarResults`: build the expressions, call `app.solution_values(...)` once, map the diagonal entries to per-winding resistance and inductance, assemble the full matrices, read `SolidLoss` into `copper_loss_w`, `CoreLoss` into `core_loss_w`, `Total_Energy` into `magnetic_energy_j`, and call `app.convergence_rows(setup)`. Wrap the whole read in one `try/except Exception` that returns `RawScalarResults(diagnostics=(f"{type(error).__name__}: {error}",))`. Impedance per winding is `R + j*2*pi*f*L` only when both parts came back, computed in the reader from the plan frequency.

Both adapters gain the stage after `analyze`:

```python
                    stages.append(StageRecord(name="results", succeeded=True, message=message))
```

where the message names how many quantities were read, and the raw results ride on the export result.

> **Live verification required before this task closes:** the three device
> expression names and the convergence source are the only parts of M8b that
> cannot be proven without AEDT. Task 8 runs them live. If AEDT names a
> quantity differently, the fix is a one-line change in
> `result_expressions.py`; if a quantity is genuinely not exposed, it stays
> `unavailable` with a reason and the name is removed from the table. Do not
> guess a value into existence.

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/unit -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/simulation/result_expressions.py src/inductor_designer/adapters/pyaedt tests
git commit -m "feat(maxwell): extract raw scalar results after the analyze stage"
```

---

### Task 5: FEMM extraction

**Files:**
- Modify: `src/inductor_designer/adapters/femm/solver.py`
- Modify: `src/inductor_designer/application/ports/femm_solver.py` (add `raw_results: RawScalarResults | None = None` to `FemmSolveResult`)
- Test: `tests/unit/adapters/test_femm_raw_results.py`

**Interfaces:**
- Consumes: the `FemmWindingResult` values the adapter already extracts.
- Produces: `FemmSolveResult.raw_results` carrying per-winding resistance, inductance and impedance, plus `copper_loss_w` computed from the reported circuit quantities. `matrices`, `core_loss_w`, `magnetic_energy_j` and `convergence` stay `None`: FEMM's circuit properties expose none of them, and the normalizer turns each into an explicit unavailable reason.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/adapters/test_femm_raw_results.py
from dataclasses import replace
from pathlib import Path

import pytest

from inductor_designer.adapters.femm.solver import PyfemmSolver
from tests.fakes.femm_module import FakeFemmModule, FakeFemmModuleFactory
from tests.unit.adapters.test_femm_solver import make_request


def solve(tmp_path: Path, **overrides: object):
    request = replace(make_request(tmp_path), **overrides)  # type: ignore[arg-type]
    return PyfemmSolver(module_factory=FakeFemmModuleFactory(FakeFemmModule())).solve(
        request
    )


def test_an_analyzed_run_reports_per_winding_scalars(tmp_path: Path) -> None:
    result = solve(tmp_path, analyze=True)

    assert result.raw_results is not None
    winding = result.raw_results.windings[0]
    assert winding.resistance_ohm is not None
    assert winding.inductance_h is not None
    assert winding.impedance is not None


def test_femm_reports_no_matrix_no_core_loss_and_no_energy(tmp_path: Path) -> None:
    raw = solve(tmp_path, analyze=True).raw_results

    assert raw is not None
    assert raw.matrices == ()
    assert raw.core_loss_w is None
    assert raw.magnetic_energy_j is None
    assert raw.convergence is None


def test_copper_loss_comes_from_the_reported_circuit_quantities(
    tmp_path: Path,
) -> None:
    raw = solve(tmp_path, analyze=True).raw_results

    assert raw is not None
    assert raw.copper_loss_w == pytest.approx(
        sum(
            0.5 * winding.resistance_ohm * abs(complex(*winding.current_a)) ** 2
            for winding in solve(tmp_path, analyze=True).results.values()  # type: ignore[union-attr]
        )
    )


def test_a_generate_only_run_reports_no_raw_results(tmp_path: Path) -> None:
    assert solve(tmp_path, analyze=False).raw_results is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/adapters/test_femm_raw_results.py -q`
Expected: FAIL, `AttributeError: 'FemmSolveResult' object has no attribute 'raw_results'`

- [ ] **Step 3: Write the implementation**

Add the field to `FemmSolveResult` and build it in `PyfemmSolver.solve` from the circuit results it already has. The peak-current convention (ADR 0006) makes the mean copper loss over a cycle `0.5 * R * |I_peak|^2`, so the conversion lives here, at the adapter boundary, with that sentence as its comment.

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/unit tests/contract -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/adapters/femm src/inductor_designer/application/ports/femm_solver.py tests
git commit -m "feat(femm): report per-winding scalars and copper loss as raw results"
```

---

### Task 6: Manifest and export files

**Files:**
- Modify: `src/inductor_designer/application/services/maxwell_export.py`
- Create: `src/inductor_designer/application/services/result_export.py`
- Modify: `src/inductor_designer/application/services/project_run.py`
- Test: `tests/unit/application/test_result_export.py`, `tests/unit/application/test_generate_and_solve.py` (extend)

**Interfaces:**
- Consumes: everything above.
- Produces: `RunManifest.results` populated for a successful solve run and `None` otherwise; `write_result_files(results_directory, result_set) -> tuple[Path, Path]` writing `results.json` and `results.csv`; two more `ManifestArtifact` entries, `results-json` and `results-csv`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/application/test_result_export.py
import csv
import json
from pathlib import Path

from inductor_designer.application.services.result_export import write_result_files
from inductor_designer.domain.project import RequestedOutput
from inductor_designer.simulation.run_contracts import (
    CurrentConvention,
    NormalizedQuantity,
    NormalizedResultSet,
    ResultAvailability,
    RunBackend,
)

RESULTS = NormalizedResultSet(
    run_id="20260810-120000",
    backend=RunBackend.FEMM,
    quantities=(
        NormalizedQuantity(
            quantity=RequestedOutput.RESISTANCE,
            scope="winding.w1",
            availability=ResultAvailability.AVAILABLE,
            value=0.125,
            unit="ohm",
            current_convention=CurrentConvention.NOT_APPLICABLE,
            approximation=None,
            reason=None,
            provenance="FEMM circuit properties",
        ),
        NormalizedQuantity(
            quantity=RequestedOutput.CORE_LOSS,
            scope="device",
            availability=ResultAvailability.UNAVAILABLE,
            value=None,
            unit=None,
            current_convention=CurrentConvention.AC_RMS,
            approximation=None,
            reason="core-loss.not_reported: FEMM does not report a core loss.",
            provenance=None,
        ),
    ),
)


def test_both_files_land_in_the_results_directory(tmp_path: Path) -> None:
    json_path, csv_path = write_result_files(tmp_path, RESULTS)

    assert json_path == tmp_path / "results.json"
    assert csv_path == tmp_path / "results.csv"


def test_the_json_carries_the_full_provenance(tmp_path: Path) -> None:
    json_path, _ = write_result_files(tmp_path, RESULTS)

    document = json.loads(json_path.read_text(encoding="utf-8"))
    assert document["runId"] == "20260810-120000"
    assert document["quantities"][0]["provenance"] == "FEMM circuit properties"


def test_the_csv_keeps_one_row_per_quantity_including_unavailable_ones(
    tmp_path: Path,
) -> None:
    _, csv_path = write_result_files(tmp_path, RESULTS)

    rows = list(csv.DictReader(csv_path.read_text(encoding="utf-8").splitlines()))
    assert [row["quantity"] for row in rows] == ["resistance", "core-loss"]
    assert rows[0]["value"] == "0.125"
    assert rows[1]["value"] == ""
    assert rows[1]["reason"].startswith("core-loss.not_reported")


def test_the_csv_header_is_stable(tmp_path: Path) -> None:
    _, csv_path = write_result_files(tmp_path, RESULTS)

    header = csv_path.read_text(encoding="utf-8").splitlines()[0]
    assert header == (
        "quantity,scope,availability,value,unit,currentConvention,"
        "approximation,reason,provenance"
    )
```

Extend `tests/unit/application/test_generate_and_solve.py`:

```python
def test_a_solved_run_populates_the_manifest_results(tmp_path: Path) -> None:
    result = solve_run(tmp_path, RunBackend.FEMM)

    assert result.outcome.manifest.results is not None
    document = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert document["results"]["quantities"]


def test_a_generate_only_run_still_has_no_results(tmp_path: Path) -> None:
    result = generate_only_run(tmp_path)

    assert result.outcome.manifest.results is None
    assert not (result.location.results_directory / "results.json").exists()


def test_the_export_files_land_beside_the_solve_log(tmp_path: Path) -> None:
    result = solve_run(tmp_path, RunBackend.FEMM)

    directory = result.location.results_directory
    assert (directory / "results.json").is_file()
    assert (directory / "results.csv").is_file()
    document = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    kinds = {artifact["kind"] for artifact in document["artifacts"]}
    assert {"results-json", "results-csv", "solve-log"} <= kinds
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/application -q`
Expected: FAIL on the missing module and the `None` manifest results

- [ ] **Step 3: Write the implementation**

`maxwell_export.py` calls `normalize_scalar_results` when the adapter returned `raw_results` and the run mode is `generate-and-solve`, and passes the result set into `_build_manifest`. `result_export.py` reuses the existing `_results_to_document` shape for JSON — export and manifest must not drift — and writes the CSV with `csv.DictWriter` and the stable header above. `project_run.py` writes both files next to the solve log and appends their artifacts, exactly as it already does for `solve-log`.

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest -n 8 -m "not aedt and not femm" -q`
Expected: all passed; the M6 golden Generate Only manifests must still match byte for byte

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/application tests
git commit -m "feat(simulation): populate manifest results and export results.json and results.csv"
```

---

### Task 7: The Review results section

**Files:**
- Modify: `src/inductor_designer/ui/review_controller.py`
- Modify: `src/inductor_designer/ui/qml/ReviewPage.qml`
- Test: `tests/ui/test_review_results_section.py`

**Interfaces:**
- Consumes: `GenerationController.last_result_set` (new: the controller keeps the last successful run's `NormalizedResultSet`, as it already keeps `failed_manifest`).
- Produces: a `Results` section in `ReviewController.sections`, one row per quantity, with the value formatted in engineering units through the existing `ui/preliminary_rows.py` conversion module, and an explicit reason line for each unavailable quantity.

- [ ] **Step 1: Write the failing test**

```python
# tests/ui/test_review_results_section.py
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from tests.ui.review_fixtures import review_with_results  # noqa: E402

pytestmark = pytest.mark.ui


def test_the_results_section_appears_after_a_solved_run() -> None:
    controller = review_with_results()

    titles = [section["title"] for section in controller.sections]
    assert "Results" in titles


def test_an_available_quantity_shows_its_value_and_unit() -> None:
    controller = review_with_results()

    rows = next(
        section["rows"] for section in controller.sections if section["title"] == "Results"
    )
    resistance = next(row for row in rows if row["label"].startswith("Resistance"))
    assert "mΩ" in resistance["value"] or "ohm" in resistance["value"]


def test_an_unavailable_quantity_shows_its_reason_not_a_blank() -> None:
    controller = review_with_results()

    rows = next(
        section["rows"] for section in controller.sections if section["title"] == "Results"
    )
    core_loss = next(row for row in rows if row["label"].startswith("Core loss"))
    assert "not reported" in core_loss["value"].casefold()


def test_no_results_section_before_any_solved_run() -> None:
    from tests.ui.review_fixtures import review_without_results

    controller = review_without_results()

    assert "Results" not in [section["title"] for section in controller.sections]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `set QT_QPA_PLATFORM=offscreen && .venv/Scripts/python.exe -m pytest tests/ui/test_review_results_section.py -q`
Expected: FAIL, no `Results` section

- [ ] **Step 3: Write the implementation**

`GenerationController` keeps `last_result_set` beside `failed_manifest`, set from `GenerationResult`. `run_generation` puts `result.outcome.manifest.results` on the `GenerationResult`. `ReviewController._results_rows()` renders one row per quantity: label from the quantity and scope, value formatted with the existing engineering-unit conversions, and the reason text when unavailable. The QML section reuses the existing section repeater; no new component.

- [ ] **Step 4: Run the tests**

Run: `set QT_QPA_PLATFORM=offscreen && set QSG_RHI_BACKEND=software && .venv/Scripts/python.exe -m pytest tests/ui -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/ui tests/ui
git commit -m "feat(ui): show the normalized results on the Review screen"
```

---

### Task 8: Live verification and acceptance evidence

**Files:**
- Create: `tests/integration/aedt/test_maxwell_results_live.py`
- Create: `tests/integration/femm/test_femm_results_live.py`
- Create: `docs/development/m8b-results-evidence.md`
- Modify: `docs/development/ROADMAP.md`, `docs/superpowers/plans/README.md`

**Interfaces:**
- Consumes: the whole slice. No code interface.

- [ ] **Step 1: Write the live tests**

Both mirror the M8a live tests: run one `generate-and-solve` run per backend, then assert that `results.json` exists, that every requested scalar quantity appears exactly once per scope, and that each entry is either available with a unit and a provenance or unavailable with a dotted reason. The test asserts the shape, never a physical value: this proves the contract, not the physics.

- [ ] **Step 2: Run the non-live gate**

```bash
.venv/Scripts/python.exe -m ruff check .
```

Expected: `All checks passed!`

```bash
.venv/Scripts/python.exe -m mypy src tools
```

Expected: `Success: no issues found`

```bash
.venv/Scripts/python.exe -m pytest -n 8 -m "not aedt and not femm" -q
```

Expected: all passed; record the exact count and duration

- [ ] **Step 3: Run the live suites on the Windows workstation**

```bash
.venv/Scripts/python.exe -m pytest -m aedt -q
```

```bash
.venv/Scripts/python.exe -m pytest -m femm -q
```

This is where the Maxwell expression names in `result_expressions.py` are proven. A name AEDT does not recognize returns no data, which surfaces as an `unavailable` quantity with a reason and a diagnostic in `results.json` — not as a wrong number. Fix the table, or accept the quantity as genuinely not exposed and remove it, and re-run.

- [ ] **Step 4: Write the evidence document**

`docs/development/m8b-results-evidence.md` records, per backend, the exact `results.json` from one run: which quantities came back available with which units and provenance, and every unavailable quantity with its reason. That table is the M8b exit criterion made concrete.

- [ ] **Step 5: Update the roadmap and the plan index**

State that M8b is implementation-complete and awaiting Fabio Posser's acceptance, and that M8c still owns every field quantity.

- [ ] **Step 6: Commit**

```bash
git add docs tests/integration
git commit -m "docs: record M8b normalized result evidence"
```

---

## Self-Review

**Spec coverage against roadmap realignment section 8 and the M8 milestone list:** resistance, inductance and complex impedance per winding — Tasks 3, 4, 5. Matrices where the backend exposes them without reinterpretation — Tasks 3, 4, with FEMM explicitly unavailable in Task 5. Copper, core and total loss — Tasks 3, 4, 5, with the labelled derivation from decision 3. Magnetic energy — Tasks 3, 4. Convergence history, final state, solver status and diagnostics — Tasks 3, 4. Backend, dimensional representation, unit, current convention, approximation status and availability on every quantity — Tasks 1, 3, carried by the existing `NormalizedQuantity` contract. JSON and CSV export — Task 6. Result availability and approximation warnings presented to the user — Task 7. Field quantities and representative cross sections — deliberately **not** here; M8c owns them, and the Scope section says so.

**Placeholder scan:** no TBD, no "handle edge cases". The one genuinely unproven element, the Maxwell expression names, is called out explicitly in Task 4 with the exact live command that proves it and the exact fix if it is wrong — that is a stated risk with a resolution path, not a placeholder.

**Type consistency:** `RawScalarResults`, `RawWindingResult`, `RawMatrix`, `RawConvergence` are defined in Task 2 and consumed under those names in Tasks 3, 4, 5. `normalize_scalar_results` is defined in Task 3 and called in Task 6. `write_result_files` is defined and called in Task 6. `unit_for`, `convention_for`, `winding_scope`, `reason_code` and `DEVICE_SCOPE` come from Task 1 and are used in Task 3.

**Known risk to raise at review:** `SolidLoss`, `CoreLoss` and `Total_Energy` are the Maxwell report-quantity names this plan assumes, and the convergence source is `app.convergence_rows`, whose PyAEDT implementation is not settled — `Setup` exposes `get_profile` but no convergence accessor, so the reader may need `post.get_solution_data` with the adaptive-cost report category instead. Both are isolated behind one pure table and one adapter method precisely so the live run can correct them without touching normalization, export or the UI.
