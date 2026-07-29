# M7a Solver-Independent Preliminary Estimator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compute preliminary flux density, current density, wire loss, and core
loss from a saved Project with no Qt, Maxwell, or FEMM involvement, reporting
each quantity independently as Estimated, Unavailable, or Invalid with a stable
diagnostic code.

**Architecture:** Four focused solver-independent modules under
`src/inductor_designer/simulation/` — shared result contracts, the magnetic
estimate, the winding estimate, and the core-loss estimate — composed by one
public entry point. Each quantity is evaluated independently so a missing loss
curve cannot suppress a valid flux density. The estimator consumes the M6
`InductorProject` aggregate, catalog records, the pinned material snapshot, and
the existing geometry packing result, and returns one immutable result object.

**Tech Stack:** Python 3.10–3.13, frozen dataclasses and enums, `math` only
(no NumPy), pytest, Ruff, strict mypy.

## Global Constraints

- Owner: one executor per working tree. Do not run two agents in the same tree.
- Entry condition: M6 is accepted; `main` starts at `ffbb281`.
- Branch: `m7a/preliminary-estimator`. Squash-merge to `main` after the final
  whole-branch review.
- This plan implements sections 5–8 of
  `docs/superpowers/specs/2026-07-26-preliminary-calculations-and-guided-flow-design.md`.
  Do not reopen its approved product or physics decisions.
- Scope is the estimator only. No Qt file, no QML, no run-directory work, no
  Guided Studio screen changes. Those belong to M7b and M7c.
- The estimator must not import Qt, PyAEDT, FEMM, SQLite, or operating-system
  APIs. `tools/check_architecture.py` already forbids these for
  `inductor_designer.simulation`; keep it passing.
- English for code, tests, docs, diagnostics, and commits.
- Every value is SI internally: `H` in A/m, `B` in T, `J` in A/m², loss in W,
  volumetric loss in W/m³, length in m, area in m².
- Copper constants, copied verbatim from the specification:
  `rho_20 = 1.7241e-8` ohm metre, `alpha_20 = 0.00393` per degree Celsius,
  valid winding-temperature range `10 °C` through `100 °C` inclusive.
- Interpolation is permitted only inside a recorded data range. Extrapolation,
  temperature correction, DC-bias correction, waveform correction, and material
  substitution are forbidden; report Unavailable instead.
- A B-H or loss series supports a requested temperature only on **exact**
  equality with `core_temperature_c`. When nothing matches, the diagnostic must
  name the temperatures that do exist so the user can choose one.
- Diagnostic codes are lowercase dotted strings, `<quantity>.<reason>`. Codes are
  a stable public contract: never reuse or repurpose an existing code string.
- Per-winding wire losses may be summed. A total that needs a missing component
  is Unavailable, never a partial sum.
- Preliminary results are derived data. Never persist them into the Project
  document.
- Run these gates before every commit:
  `.venv/Scripts/python.exe -m pytest tests -q -m "not aedt and not femm"`,
  `.venv/Scripts/python.exe -m ruff check .`,
  `.venv/Scripts/python.exe -m mypy src tools`,
  `.venv/Scripts/python.exe tools/check_architecture.py`,
  `git diff --check`.

## M6 contracts this plan consumes

Read these before Task 1; the plan relies on their exact field names.

| Type | Location | Fields used |
| --- | --- | --- |
| `InductorProject` | `src/inductor_designer/domain/project.py:166` | `design`, `operating_point` |
| `Design` | `domain/project.py:96` | `core`, `windings`, `core_material`, `manual_material_compatibility_acknowledged` |
| `OperatingPoint` | `domain/project.py:129` | `frequency_hz`, `winding_temperature_c`, `core_temperature_c`, `windings` |
| `WindingOperatingPoint` | `domain/project.py:105` | `winding_id`, `ac_rms_current_a`, `ac_phase_deg`, `dc_current_a`, `current_direction` |
| `CurrentDirection` | `domain/winding.py:17` | `FORWARD`, `REVERSE` |
| `MaterialRevisionSelection` | `domain/project.py:63` | `revision_id`, `snapshot`, `bh_series_id` |
| `MaterialRecord` | `materials/records.py:96` | `series`, `relative_permeability`, `steinmetz` |
| `PointSeries` | `materials/records.py:71` | `series_id`, `kind`, `conditions`, `points` |
| `CurveConditions` | `materials/records.py:48` | `frequency_hz`, `temperature_c`, `dc_bias_a_per_m` |
| `SteinmetzFit` | `materials/records.py:82` | `k`, `alpha`, `beta` |
| `CoreRecord` | `domain/catalog_records.py:42` | `effective_area_m2`, `path_length_m`, `volume_m3` |
| `ConductorRecord` | `domain/catalog_records.py:78` | `bare_diameter_m` |
| `PackedWinding` | `geometry/packing.py:37` | `winding_id`, `wire_length_m` |

Canonical series orientation, already guaranteed by the material pipeline:

- B-H series: each `CurvePoint.x` is `H` in A/m, `.y` is `B` in T.
- Loss series: each `CurvePoint.x` is `B` in T, `.y` is volumetric loss in W/m³.

## Expected outcome for the M5a sample material

`Magnetics / High Flux / 60` revision `94e880a99b98` carries loss series recorded
at `dc_bias_a_per_m = 0.0`. A project with nonzero DC current therefore produces
`core_loss` Unavailable with code `core_loss.no_loss_data_for_dc_bias`, while
flux density, current density, and wire loss remain Estimated. That is correct
behaviour under specification section 8 — do not "fix" it by interpolating or by
ignoring the DC-bias condition.

---

### Task 1: Result contracts and diagnostic codes

**Files:**
- Create: `src/inductor_designer/simulation/preliminary_contracts.py`
- Test: `tests/unit/simulation/test_preliminary_contracts.py`

**Interfaces:**
- Produces: `ResultState`, `PreliminaryValue`, `estimated(value, notes=())`,
  `unavailable(code, message)`, `invalid(code, message)`, and the `DiagnosticCode`
  string constants used by Tasks 2–6.
- Consumes: nothing.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/simulation/test_preliminary_contracts.py`:

```python
from __future__ import annotations

import pytest

from inductor_designer.simulation.preliminary_contracts import (
    DiagnosticCode,
    PreliminaryValue,
    ResultState,
    estimated,
    invalid,
    unavailable,
)


def test_estimated_value_carries_a_number_and_no_diagnostic() -> None:
    value = estimated(1.25, notes=("linear permeability approximation",))

    assert value.state is ResultState.ESTIMATED
    assert value.value == 1.25
    assert value.code is None
    assert value.message is None
    assert value.notes == ("linear permeability approximation",)


def test_unavailable_value_carries_a_code_and_message_but_no_number() -> None:
    value = unavailable(
        DiagnosticCode.CORE_LOSS_NO_LOSS_DATA_FOR_DC_BIAS,
        "No loss data recorded at 1800 A/m DC bias; recorded bias: 0 A/m.",
    )

    assert value.state is ResultState.UNAVAILABLE
    assert value.value is None
    assert value.code == "core_loss.no_loss_data_for_dc_bias"
    assert "1800 A/m" in str(value.message)


def test_invalid_value_is_distinct_from_unavailable() -> None:
    value = invalid(
        DiagnosticCode.WIRE_LOSS_TEMPERATURE_OUT_OF_RANGE,
        "Winding temperature 150 C is outside 10 C through 100 C.",
    )

    assert value.state is ResultState.INVALID
    assert value.value is None


def test_estimated_requires_a_finite_number() -> None:
    with pytest.raises(ValueError, match="finite"):
        estimated(float("nan"))


def test_a_diagnostic_state_requires_both_code_and_message() -> None:
    with pytest.raises(ValueError, match="code and message"):
        PreliminaryValue(state=ResultState.UNAVAILABLE, value=None, code=None, message=None)


def test_every_diagnostic_code_is_a_dotted_lowercase_string() -> None:
    codes = [
        getattr(DiagnosticCode, name)
        for name in dir(DiagnosticCode)
        if name.isupper()
    ]

    assert codes, "DiagnosticCode must define codes"
    for code in codes:
        assert code == code.lower(), code
        quantity, _, reason = code.partition(".")
        assert quantity and reason, code
        assert " " not in code, code
    assert len(set(codes)) == len(codes), "diagnostic codes must be unique"
```

- [ ] **Step 2: Run the test and verify RED**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/simulation/test_preliminary_contracts.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named
'inductor_designer.simulation.preliminary_contracts'`.

- [ ] **Step 3: Implement the contracts**

Create `src/inductor_designer/simulation/preliminary_contracts.py`:

```python
"""Result states and stable diagnostic codes for preliminary estimates.

Every quantity is reported independently: a missing loss curve makes core loss
unavailable without disturbing flux density, current density, or wire loss.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import isfinite


class ResultState(str, Enum):
    """Exactly the three states specification section 4.3 allows."""

    ESTIMATED = "estimated"
    UNAVAILABLE = "unavailable"
    INVALID = "invalid"


class DiagnosticCode:
    """Stable `<quantity>.<reason>` codes.

    These strings appear in the UI, in logs, and in M7b run manifests. Never
    reuse or repurpose one: add a new code instead.
    """

    FLUX_DENSITY_NO_CORE_SELECTED = "flux_density.no_core_selected"
    FLUX_DENSITY_NO_MATERIAL_SELECTED = "flux_density.no_material_selected"
    FLUX_DENSITY_NO_BH_SERIES_FOR_TEMPERATURE = (
        "flux_density.no_bh_series_for_temperature"
    )
    FLUX_DENSITY_NO_SUPPORTED_MODEL = "flux_density.no_supported_model"
    FLUX_DENSITY_FIELD_OUTSIDE_BH_RANGE = "flux_density.field_outside_bh_range"
    FLUX_DENSITY_NON_POSITIVE_PATH_LENGTH = "flux_density.non_positive_path_length"

    CURRENT_DENSITY_NO_CONDUCTOR = "current_density.no_conductor"

    WIRE_LOSS_NO_GEOMETRY = "wire_loss.no_geometry"
    WIRE_LOSS_TEMPERATURE_OUT_OF_RANGE = "wire_loss.temperature_out_of_range"

    CORE_LOSS_NO_FLUX_DENSITY = "core_loss.no_flux_density"
    CORE_LOSS_NON_POSITIVE_FREQUENCY = "core_loss.non_positive_frequency"
    CORE_LOSS_NON_POSITIVE_VOLUME = "core_loss.non_positive_volume"
    CORE_LOSS_NO_LOSS_DATA_FOR_TEMPERATURE = "core_loss.no_loss_data_for_temperature"
    CORE_LOSS_NO_LOSS_DATA_FOR_DC_BIAS = "core_loss.no_loss_data_for_dc_bias"
    CORE_LOSS_FLUX_OUTSIDE_LOSS_RANGE = "core_loss.flux_outside_loss_range"
    CORE_LOSS_FREQUENCY_OUTSIDE_FIT_ENVELOPE = (
        "core_loss.frequency_outside_fit_envelope"
    )
    CORE_LOSS_NO_LOSS_MODEL = "core_loss.no_loss_model"

    TOTAL_LOSS_INCOMPLETE = "total_loss.incomplete"


@dataclass(frozen=True, slots=True)
class PreliminaryValue:
    """One reported quantity in exactly one state."""

    state: ResultState
    value: float | None
    code: str | None = None
    message: str | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.state is ResultState.ESTIMATED:
            if self.value is None or not isfinite(self.value):
                raise ValueError("an estimated value must be a finite number")
            if self.code is not None or self.message is not None:
                raise ValueError("an estimated value carries no diagnostic")
            return
        if self.value is not None:
            raise ValueError(f"a {self.state.value} value carries no number")
        if not self.code or not self.message:
            raise ValueError(
                f"a {self.state.value} value requires both code and message"
            )


def estimated(value: float, notes: tuple[str, ...] = ()) -> PreliminaryValue:
    return PreliminaryValue(state=ResultState.ESTIMATED, value=value, notes=notes)


def unavailable(code: str, message: str) -> PreliminaryValue:
    return PreliminaryValue(
        state=ResultState.UNAVAILABLE, value=None, code=code, message=message
    )


def invalid(code: str, message: str) -> PreliminaryValue:
    return PreliminaryValue(
        state=ResultState.INVALID, value=None, code=code, message=message
    )
```

- [ ] **Step 4: Run the test and verify GREEN**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/simulation/test_preliminary_contracts.py -q`
Expected: `6 passed`.

- [ ] **Step 5: Run the gates and commit**

```bash
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy src tools
.venv/Scripts/python.exe tools/check_architecture.py
git add src/inductor_designer/simulation/preliminary_contracts.py tests/unit/simulation/test_preliminary_contracts.py
git commit -m "feat(simulation): add preliminary result states and diagnostic codes"
```

---

### Task 2: Ampere-turns and magnetic field strength

**Files:**
- Create: `src/inductor_designer/simulation/magnetic_estimate.py`
- Test: `tests/unit/simulation/test_magnetic_estimate.py`

**Interfaces:**
- Consumes: Task 1 contracts.
- Produces: `FieldStrengths` with fields `h_ac_peak_a_per_m`, `h_dc_a_per_m`,
  `h_min_a_per_m`, `h_max_a_per_m`; and
  `field_strengths(operating_point, turns_by_winding, path_length_m) ->
  FieldStrengths | PreliminaryValue` where a `PreliminaryValue` is the failure.

Specification section 6, verbatim:

```text
A_AC_peak = sum_k(s_k * N_k * sqrt(2) * I_rms,k * exp(j * phi_k))
A_DC      = sum_k(s_k * N_k * I_dc,k)
H_AC_peak = abs(A_AC_peak) / l_e
H_DC      = A_DC / l_e
H_min     = H_DC - H_AC_peak
H_max     = H_DC + H_AC_peak
```

- [ ] **Step 1: Write the failing test**

Create `tests/unit/simulation/test_magnetic_estimate.py`:

```python
from __future__ import annotations

import math

from inductor_designer.domain.project import OperatingPoint, WindingOperatingPoint
from inductor_designer.domain.winding import CurrentDirection
from inductor_designer.simulation.magnetic_estimate import (
    FieldStrengths,
    field_strengths,
)
from inductor_designer.simulation.preliminary_contracts import (
    DiagnosticCode,
    PreliminaryValue,
)


def _operating_point(*windings: WindingOperatingPoint) -> OperatingPoint:
    return OperatingPoint(frequency_hz=100_000.0, windings=windings)


def _winding(
    winding_id: str,
    *,
    ac_rms: float = 0.0,
    phase_deg: float = 0.0,
    dc: float = 0.0,
    direction: CurrentDirection = CurrentDirection.FORWARD,
) -> WindingOperatingPoint:
    return WindingOperatingPoint(
        winding_id=winding_id,
        ac_rms_current_a=ac_rms,
        ac_phase_deg=phase_deg,
        dc_current_a=dc,
        current_direction=direction,
    )


def test_single_winding_ac_peak_uses_sqrt_two_times_rms() -> None:
    result = field_strengths(
        _operating_point(_winding("w1", ac_rms=2.0)),
        {"w1": 10},
        path_length_m=0.1,
    )

    assert isinstance(result, FieldStrengths)
    # 10 turns * sqrt(2) * 2 A / 0.1 m
    assert result.h_ac_peak_a_per_m == 10 * math.sqrt(2) * 2.0 / 0.1
    assert result.h_dc_a_per_m == 0.0
    assert result.h_min_a_per_m == -result.h_ac_peak_a_per_m
    assert result.h_max_a_per_m == result.h_ac_peak_a_per_m


def test_in_phase_windings_add_and_reverse_direction_subtracts() -> None:
    same = field_strengths(
        _operating_point(_winding("w1", ac_rms=1.0), _winding("w2", ac_rms=1.0)),
        {"w1": 10, "w2": 10},
        path_length_m=0.1,
    )
    opposed = field_strengths(
        _operating_point(
            _winding("w1", ac_rms=1.0),
            _winding("w2", ac_rms=1.0, direction=CurrentDirection.REVERSE),
        ),
        {"w1": 10, "w2": 10},
        path_length_m=0.1,
    )

    assert isinstance(same, FieldStrengths)
    assert isinstance(opposed, FieldStrengths)
    assert math.isclose(same.h_ac_peak_a_per_m, 2 * 10 * math.sqrt(2) / 0.1)
    assert math.isclose(opposed.h_ac_peak_a_per_m, 0.0, abs_tol=1e-9)


def test_quadrature_phases_combine_as_phasors_not_magnitudes() -> None:
    result = field_strengths(
        _operating_point(
            _winding("w1", ac_rms=1.0, phase_deg=0.0),
            _winding("w2", ac_rms=1.0, phase_deg=90.0),
        ),
        {"w1": 10, "w2": 10},
        path_length_m=0.1,
    )

    assert isinstance(result, FieldStrengths)
    single = 10 * math.sqrt(2) * 1.0 / 0.1
    assert math.isclose(result.h_ac_peak_a_per_m, single * math.sqrt(2))


def test_dc_ampere_turns_are_summed_separately_and_shift_the_window() -> None:
    result = field_strengths(
        _operating_point(_winding("w1", ac_rms=1.0, dc=5.0)),
        {"w1": 10},
        path_length_m=0.1,
    )

    assert isinstance(result, FieldStrengths)
    assert result.h_dc_a_per_m == 10 * 5.0 / 0.1
    assert math.isclose(
        result.h_min_a_per_m, result.h_dc_a_per_m - result.h_ac_peak_a_per_m
    )
    assert math.isclose(
        result.h_max_a_per_m, result.h_dc_a_per_m + result.h_ac_peak_a_per_m
    )


def test_reverse_direction_flips_the_dc_contribution() -> None:
    result = field_strengths(
        _operating_point(
            _winding("w1", dc=5.0, direction=CurrentDirection.REVERSE)
        ),
        {"w1": 10},
        path_length_m=0.1,
    )

    assert isinstance(result, FieldStrengths)
    assert result.h_dc_a_per_m == -10 * 5.0 / 0.1


def test_non_positive_path_length_is_a_diagnostic_not_a_crash() -> None:
    result = field_strengths(
        _operating_point(_winding("w1", ac_rms=1.0)),
        {"w1": 10},
        path_length_m=0.0,
    )

    assert isinstance(result, PreliminaryValue)
    assert result.code == DiagnosticCode.FLUX_DENSITY_NON_POSITIVE_PATH_LENGTH


def test_a_winding_without_a_turn_count_contributes_nothing() -> None:
    result = field_strengths(
        _operating_point(_winding("w1", ac_rms=1.0), _winding("w2", ac_rms=1.0)),
        {"w1": 10},
        path_length_m=0.1,
    )

    assert isinstance(result, FieldStrengths)
    assert math.isclose(result.h_ac_peak_a_per_m, 10 * math.sqrt(2) / 0.1)
```

- [ ] **Step 2: Run the test and verify RED**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/simulation/test_magnetic_estimate.py -q`
Expected: FAIL with `ModuleNotFoundError` for
`inductor_designer.simulation.magnetic_estimate`.

- [ ] **Step 3: Implement field strengths**

Create `src/inductor_designer/simulation/magnetic_estimate.py`:

```python
"""Lumped effective-core magnetic estimate (specification section 6).

The result is a lumped effective-core value. It is not a local maximum, an
area-weighted mean, a leakage-field result, or a replacement for Maxwell/FEMM
field extraction.
"""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass
from collections.abc import Mapping

from inductor_designer.domain.project import OperatingPoint
from inductor_designer.domain.winding import CurrentDirection
from inductor_designer.simulation.preliminary_contracts import (
    DiagnosticCode,
    PreliminaryValue,
    unavailable,
)


@dataclass(frozen=True, slots=True)
class FieldStrengths:
    h_ac_peak_a_per_m: float
    h_dc_a_per_m: float
    h_min_a_per_m: float
    h_max_a_per_m: float


def _sign(direction: CurrentDirection) -> float:
    return 1.0 if direction is CurrentDirection.FORWARD else -1.0


def field_strengths(
    operating_point: OperatingPoint,
    turns_by_winding: Mapping[str, int],
    path_length_m: float,
) -> FieldStrengths | PreliminaryValue:
    """Return field strengths, or the diagnostic explaining why they are absent."""
    if not path_length_m > 0.0:
        return unavailable(
            DiagnosticCode.FLUX_DENSITY_NON_POSITIVE_PATH_LENGTH,
            "Core effective magnetic path length must be positive; "
            f"got {path_length_m:g} m.",
        )

    ac_phasor = 0j
    dc_ampere_turns = 0.0
    for winding in operating_point.windings:
        turns = turns_by_winding.get(winding.winding_id)
        if turns is None:
            continue
        sign = _sign(winding.current_direction)
        ac_phasor += (
            sign
            * turns
            * math.sqrt(2.0)
            * winding.ac_rms_current_a
            * cmath.exp(1j * math.radians(winding.ac_phase_deg))
        )
        dc_ampere_turns += sign * turns * winding.dc_current_a

    h_ac_peak = abs(ac_phasor) / path_length_m
    h_dc = dc_ampere_turns / path_length_m
    return FieldStrengths(
        h_ac_peak_a_per_m=h_ac_peak,
        h_dc_a_per_m=h_dc,
        h_min_a_per_m=h_dc - h_ac_peak,
        h_max_a_per_m=h_dc + h_ac_peak,
    )
```

- [ ] **Step 4: Run the test and verify GREEN**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/simulation/test_magnetic_estimate.py -q`
Expected: `7 passed`.

- [ ] **Step 5: Run the gates and commit**

```bash
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy src tools
.venv/Scripts/python.exe tools/check_architecture.py
git add src/inductor_designer/simulation/magnetic_estimate.py tests/unit/simulation/test_magnetic_estimate.py
git commit -m "feat(simulation): estimate ampere-turns and magnetic field strength"
```

---

### Task 3: Flux density from B-H data or linear permeability

**Files:**
- Modify: `src/inductor_designer/simulation/magnetic_estimate.py`
- Test: `tests/unit/simulation/test_magnetic_estimate.py`

**Interfaces:**
- Consumes: Task 2 `FieldStrengths`; `MaterialRevisionSelection`.
- Produces: `FluxDensities` with `b_dc_t`, `b_min_t`, `b_max_t`,
  `b_ac_peak_t`, `b_peak_magnitude_t`, `notes`; and
  `flux_densities(selection, fields, core_temperature_c) ->
  FluxDensities | PreliminaryValue`.

Rules from specification section 6:

- The selected B-H series must match `core_temperature_c` exactly. When no series
  matches, report `flux_density.no_bh_series_for_temperature` and name the
  temperatures that do exist.
- Interpolate linearly inside the recorded range; never extrapolate.
- A first-quadrant monotonic series serves negative `H` by odd symmetry,
  `B(-H) = -B(H)`, and that assumption is reported in `notes`.
- With no usable series but a valid `relative_permeability`, use
  `B = mu_0 * mu_r * H`, labelled
  `linear permeability approximation; saturation and hysteresis are not modeled`.
- With neither model, flux density is Unavailable.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/simulation/test_magnetic_estimate.py`:

```python
from dataclasses import replace

from inductor_designer.domain.project import MaterialRevisionSelection
from inductor_designer.materials.identity import MaterialRef
from inductor_designer.materials.records import (
    CurveConditions,
    CurvePoint,
    MaterialRecord,
    MaterialStatus,
    PointSeries,
    SeriesKind,
    SourceKind,
    SourceProvenance,
)
from inductor_designer.simulation.magnetic_estimate import (
    FluxDensities,
    flux_densities,
)

MU_0 = 4e-7 * math.pi


def _bh_series(
    series_id: str = "bh-25c",
    temperature_c: float | None = 25.0,
    points: tuple[tuple[float, float], ...] = ((0.0, 0.0), (100.0, 0.5), (200.0, 0.8)),
) -> PointSeries:
    return PointSeries(
        series_id=series_id,
        kind=SeriesKind.BH_CURVE,
        x_unit="A/m",
        y_unit="T",
        conditions=CurveConditions(
            frequency_hz=None, temperature_c=temperature_c, dc_bias_a_per_m=None
        ),
        points=tuple(CurvePoint(h, b) for h, b in points),
        source_filename="bh.csv",
    )


def _selection(
    *,
    series: tuple[PointSeries, ...] = (),
    relative_permeability: float | None = None,
    bh_series_id: str | None = None,
) -> MaterialRevisionSelection:
    ref = MaterialRef("Magnetics", "High Flux", "60")
    record = MaterialRecord(
        ref=ref,
        revision_id="0123456789ab",
        status=MaterialStatus.IMPORTED,
        created_at="2026-07-29T00:00:00+00:00",
        reviewed_by=None,
        approved_by=None,
        sources=(
            SourceProvenance(
                kind=SourceKind.CSV,
                filename="bh.csv",
                sha256="0" * 64,
                url="",
                page=None,
                captured_at="2026-07-29T00:00:00",
                description="test",
            ),
        ),
        series=series,
        relative_permeability=relative_permeability,
        mass_density_kg_per_m3=8176.0,
        steinmetz=None,
        notes="",
    )
    return MaterialRevisionSelection(
        ref=ref,
        revision_id="0123456789ab",
        snapshot=record,
        bh_series_id=bh_series_id,
    )


def _fields(h_dc: float, h_ac_peak: float) -> FieldStrengths:
    return FieldStrengths(
        h_ac_peak_a_per_m=h_ac_peak,
        h_dc_a_per_m=h_dc,
        h_min_a_per_m=h_dc - h_ac_peak,
        h_max_a_per_m=h_dc + h_ac_peak,
    )


def test_bh_series_interpolates_linearly_inside_the_recorded_range() -> None:
    result = flux_densities(
        _selection(series=(_bh_series(),), bh_series_id="bh-25c"),
        _fields(h_dc=50.0, h_ac_peak=0.0),
        core_temperature_c=25.0,
    )

    assert isinstance(result, FluxDensities)
    assert math.isclose(result.b_dc_t, 0.25)


def test_negative_field_uses_reported_odd_symmetry() -> None:
    result = flux_densities(
        _selection(series=(_bh_series(),), bh_series_id="bh-25c"),
        _fields(h_dc=0.0, h_ac_peak=100.0),
        core_temperature_c=25.0,
    )

    assert isinstance(result, FluxDensities)
    assert math.isclose(result.b_min_t, -0.5)
    assert math.isclose(result.b_max_t, 0.5)
    assert math.isclose(result.b_ac_peak_t, 0.5)
    assert math.isclose(result.b_peak_magnitude_t, 0.5)
    assert any("odd symmetry" in note for note in result.notes)


def test_field_beyond_the_recorded_range_is_not_extrapolated() -> None:
    result = flux_densities(
        _selection(series=(_bh_series(),), bh_series_id="bh-25c"),
        _fields(h_dc=0.0, h_ac_peak=250.0),
        core_temperature_c=25.0,
    )

    assert isinstance(result, PreliminaryValue)
    assert result.code == DiagnosticCode.FLUX_DENSITY_FIELD_OUTSIDE_BH_RANGE
    assert "200" in str(result.message)


def test_temperature_mismatch_names_the_available_temperatures() -> None:
    result = flux_densities(
        _selection(series=(_bh_series(temperature_c=25.0),), bh_series_id="bh-25c"),
        _fields(h_dc=50.0, h_ac_peak=0.0),
        core_temperature_c=80.0,
    )

    assert isinstance(result, PreliminaryValue)
    assert result.code == DiagnosticCode.FLUX_DENSITY_NO_BH_SERIES_FOR_TEMPERATURE
    assert "80" in str(result.message)
    assert "25" in str(result.message)


def test_linear_permeability_fallback_is_labelled() -> None:
    result = flux_densities(
        _selection(relative_permeability=60.0),
        _fields(h_dc=1000.0, h_ac_peak=0.0),
        core_temperature_c=25.0,
    )

    assert isinstance(result, FluxDensities)
    assert math.isclose(result.b_dc_t, MU_0 * 60.0 * 1000.0)
    assert any("linear permeability approximation" in note for note in result.notes)


def test_no_model_at_all_is_unavailable() -> None:
    result = flux_densities(
        _selection(),
        _fields(h_dc=1000.0, h_ac_peak=0.0),
        core_temperature_c=25.0,
    )

    assert isinstance(result, PreliminaryValue)
    assert result.code == DiagnosticCode.FLUX_DENSITY_NO_SUPPORTED_MODEL
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/simulation/test_magnetic_estimate.py -q`
Expected: FAIL with `ImportError: cannot import name 'FluxDensities'`.

- [ ] **Step 3: Implement flux densities**

Append to `src/inductor_designer/simulation/magnetic_estimate.py`:

```python
MU_0 = 4e-7 * math.pi

_ODD_SYMMETRY_NOTE = (
    "negative field strength evaluated by odd symmetry of the first-quadrant "
    "B-H series"
)
_LINEAR_NOTE = (
    "linear permeability approximation; saturation and hysteresis are not modeled"
)


@dataclass(frozen=True, slots=True)
class FluxDensities:
    b_dc_t: float
    b_min_t: float
    b_max_t: float
    b_ac_peak_t: float
    b_peak_magnitude_t: float
    notes: tuple[str, ...]


def _interpolate(series: PointSeries, h: float) -> float | None:
    """Odd-symmetric linear interpolation; None when outside the recorded range."""
    magnitude = abs(h)
    points = sorted(series.points, key=lambda point: point.x)
    if not points or magnitude > points[-1].x:
        return None
    sign = 1.0 if h >= 0.0 else -1.0
    previous = points[0]
    for point in points:
        if point.x == magnitude:
            return sign * point.y
        if point.x > magnitude:
            span = point.x - previous.x
            if span <= 0.0:
                return sign * point.y
            fraction = (magnitude - previous.x) / span
            return sign * (previous.y + fraction * (point.y - previous.y))
        previous = point
    return sign * points[-1].y


def _selected_bh_series(
    selection: MaterialRevisionSelection, core_temperature_c: float
) -> PointSeries | None:
    candidates = [
        series
        for series in selection.snapshot.series
        if series.kind is SeriesKind.BH_CURVE
        and (selection.bh_series_id is None or series.series_id == selection.bh_series_id)
    ]
    for series in candidates:
        if series.conditions.temperature_c == core_temperature_c:
            return series
    return None


def flux_densities(
    selection: MaterialRevisionSelection,
    fields: FieldStrengths,
    core_temperature_c: float,
) -> FluxDensities | PreliminaryValue:
    """Map H to B using recorded B-H data, else a labelled linear approximation."""
    bh_series = _selected_bh_series(selection, core_temperature_c)
    if bh_series is not None:
        mapped: list[float] = []
        for h in (fields.h_min_a_per_m, fields.h_dc_a_per_m, fields.h_max_a_per_m):
            value = _interpolate(bh_series, h)
            if value is None:
                largest = max(point.x for point in bh_series.points)
                return unavailable(
                    DiagnosticCode.FLUX_DENSITY_FIELD_OUTSIDE_BH_RANGE,
                    f"Field strength {h:g} A/m is outside the recorded range of "
                    f"series {bh_series.series_id} (0 to {largest:g} A/m); "
                    "extrapolation is not performed.",
                )
            mapped.append(value)
        b_min, b_dc, b_max = mapped
        notes: tuple[str, ...] = ()
        if min(fields.h_min_a_per_m, fields.h_dc_a_per_m, fields.h_max_a_per_m) < 0.0:
            notes = (_ODD_SYMMETRY_NOTE,)
        return _assemble(b_dc, b_min, b_max, notes)

    available = sorted(
        {
            series.conditions.temperature_c
            for series in selection.snapshot.series
            if series.kind is SeriesKind.BH_CURVE
            and series.conditions.temperature_c is not None
        }
    )
    if available:
        recorded = ", ".join(f"{value:g} C" for value in available)
        return unavailable(
            DiagnosticCode.FLUX_DENSITY_NO_BH_SERIES_FOR_TEMPERATURE,
            f"No B-H series recorded at {core_temperature_c:g} C; "
            f"available: {recorded}. Set the core temperature to a recorded "
            "value or import a series at the temperature you need.",
        )

    permeability = selection.snapshot.relative_permeability
    if permeability is not None and permeability > 0.0:
        factor = MU_0 * permeability
        return _assemble(
            factor * fields.h_dc_a_per_m,
            factor * fields.h_min_a_per_m,
            factor * fields.h_max_a_per_m,
            (_LINEAR_NOTE,),
        )

    return unavailable(
        DiagnosticCode.FLUX_DENSITY_NO_SUPPORTED_MODEL,
        "The selected material revision has no B-H series and no relative "
        "permeability, so flux density cannot be estimated.",
    )


def _assemble(
    b_dc: float, b_min: float, b_max: float, notes: tuple[str, ...]
) -> FluxDensities:
    return FluxDensities(
        b_dc_t=b_dc,
        b_min_t=b_min,
        b_max_t=b_max,
        b_ac_peak_t=(b_max - b_min) / 2.0,
        b_peak_magnitude_t=max(abs(b_min), abs(b_max)),
        notes=notes,
    )
```

Add these imports at the top of the module:

```python
from inductor_designer.domain.project import MaterialRevisionSelection
from inductor_designer.materials.records import PointSeries, SeriesKind
```

- [ ] **Step 4: Run the tests and verify GREEN**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/simulation/test_magnetic_estimate.py -q`
Expected: `13 passed`.

- [ ] **Step 5: Run the gates and commit**

```bash
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy src tools
.venv/Scripts/python.exe tools/check_architecture.py
git add src/inductor_designer/simulation/magnetic_estimate.py tests/unit/simulation/test_magnetic_estimate.py
git commit -m "feat(simulation): map field strength to flux density without extrapolating"
```

---

### Task 4: Conductor area and current densities

**Files:**
- Create: `src/inductor_designer/simulation/winding_estimate.py`
- Test: `tests/unit/simulation/test_winding_estimate.py`

**Interfaces:**
- Consumes: Task 1 contracts; `ConductorRecord.bare_diameter_m`.
- Produces: `conductor_area_m2(bare_diameter_m) -> float`;
  `current_densities(area_m2, ac_rms_current_a, dc_current_a) ->
  CurrentDensities` with `j_ac_rms_a_per_m2`, `j_ac_peak_a_per_m2`,
  `j_dc_a_per_m2`.

Specification section 7, verbatim:

```text
A_copper  = pi * d_bare^2 / 4
J_AC_RMS  = I_AC_RMS / A_copper
J_AC_peak = sqrt(2) * J_AC_RMS
J_DC      = I_DC / A_copper
```

- [ ] **Step 1: Write the failing test**

Create `tests/unit/simulation/test_winding_estimate.py`:

```python
from __future__ import annotations

import math

import pytest

from inductor_designer.simulation.winding_estimate import (
    CurrentDensities,
    conductor_area_m2,
    current_densities,
)


def test_conductor_area_is_the_bare_circle_area() -> None:
    assert math.isclose(conductor_area_m2(0.001), math.pi * 0.001**2 / 4.0)


def test_current_densities_use_the_copper_area() -> None:
    area = conductor_area_m2(0.001)

    result = current_densities(area, ac_rms_current_a=2.0, dc_current_a=5.0)

    assert isinstance(result, CurrentDensities)
    assert math.isclose(result.j_ac_rms_a_per_m2, 2.0 / area)
    assert math.isclose(result.j_ac_peak_a_per_m2, math.sqrt(2.0) * 2.0 / area)
    assert math.isclose(result.j_dc_a_per_m2, 5.0 / area)


def test_zero_currents_give_zero_densities_not_a_diagnostic() -> None:
    result = current_densities(conductor_area_m2(0.001), 0.0, 0.0)

    assert result.j_ac_rms_a_per_m2 == 0.0
    assert result.j_dc_a_per_m2 == 0.0


def test_non_positive_diameter_is_rejected_at_the_boundary() -> None:
    with pytest.raises(ValueError, match="positive"):
        conductor_area_m2(0.0)
```

- [ ] **Step 2: Run the test and verify RED**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/simulation/test_winding_estimate.py -q`
Expected: FAIL with `ModuleNotFoundError` for
`inductor_designer.simulation.winding_estimate`.

- [ ] **Step 3: Implement area and current densities**

Create `src/inductor_designer/simulation/winding_estimate.py`:

```python
"""Per-winding preliminary estimates (specification section 7).

Current density is uniform over the copper area. Skin and proximity
redistribution are excluded.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CurrentDensities:
    j_ac_rms_a_per_m2: float
    j_ac_peak_a_per_m2: float
    j_dc_a_per_m2: float


def conductor_area_m2(bare_diameter_m: float) -> float:
    if not bare_diameter_m > 0.0:
        raise ValueError("bare conductor diameter must be positive")
    return math.pi * bare_diameter_m**2 / 4.0


def current_densities(
    area_m2: float, ac_rms_current_a: float, dc_current_a: float
) -> CurrentDensities:
    j_ac_rms = ac_rms_current_a / area_m2
    return CurrentDensities(
        j_ac_rms_a_per_m2=j_ac_rms,
        j_ac_peak_a_per_m2=math.sqrt(2.0) * j_ac_rms,
        j_dc_a_per_m2=dc_current_a / area_m2,
    )
```

- [ ] **Step 4: Run the test and verify GREEN**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/simulation/test_winding_estimate.py -q`
Expected: `4 passed`.

- [ ] **Step 5: Run the gates and commit**

```bash
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy src tools
.venv/Scripts/python.exe tools/check_architecture.py
git add src/inductor_designer/simulation/winding_estimate.py tests/unit/simulation/test_winding_estimate.py
git commit -m "feat(simulation): estimate conductor area and current densities"
```

---

### Task 5: Copper resistance and wire loss

**Files:**
- Modify: `src/inductor_designer/simulation/winding_estimate.py`
- Test: `tests/unit/simulation/test_winding_estimate.py`

**Interfaces:**
- Consumes: Task 4 `conductor_area_m2`; `PackedWinding.wire_length_m`.
- Produces: `COPPER_RHO_20_OHM_M`, `COPPER_ALPHA_20_PER_C`,
  `COPPER_MIN_TEMPERATURE_C`, `COPPER_MAX_TEMPERATURE_C`,
  `WIRE_LOSS_EXCLUSION_NOTE`, `LEAD_EXCLUSION_NOTE`, and
  `wire_resistance_and_loss(area_m2, wire_length_m, winding_temperature_c,
  ac_rms_current_a, dc_current_a) -> WireLoss | PreliminaryValue` with
  `WireLoss` fields `resistance_ohm`, `loss_w`, `notes`.

Specification section 7, verbatim:

```text
rho(T_w)  = rho_20 * (1 + alpha_20 * (T_w - 20 °C))
R_DC(T_w) = rho(T_w) * wire_length / A_copper
P_wire    = R_DC(T_w) * (I_AC_RMS^2 + I_DC^2)
rho_20    = 1.7241e-8 ohm metre
alpha_20  = 0.00393 per degree Celsius
valid winding-temperature range = 10 °C through 100 °C
```

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/simulation/test_winding_estimate.py`:

```python
from inductor_designer.simulation.preliminary_contracts import (
    DiagnosticCode,
    PreliminaryValue,
)
from inductor_designer.simulation.winding_estimate import (
    COPPER_ALPHA_20_PER_C,
    COPPER_RHO_20_OHM_M,
    WireLoss,
    wire_resistance_and_loss,
)


def test_copper_constants_match_the_specification_exactly() -> None:
    assert COPPER_RHO_20_OHM_M == 1.7241e-8
    assert COPPER_ALPHA_20_PER_C == 0.00393


def test_resistance_at_twenty_degrees_uses_rho_twenty_directly() -> None:
    area = conductor_area_m2(0.001)

    result = wire_resistance_and_loss(area, 2.0, 20.0, 1.0, 0.0)

    assert isinstance(result, WireLoss)
    assert math.isclose(result.resistance_ohm, COPPER_RHO_20_OHM_M * 2.0 / area)


def test_resistance_rises_linearly_with_winding_temperature() -> None:
    area = conductor_area_m2(0.001)

    result = wire_resistance_and_loss(area, 2.0, 100.0, 1.0, 0.0)

    expected_rho = COPPER_RHO_20_OHM_M * (1.0 + COPPER_ALPHA_20_PER_C * 80.0)
    assert isinstance(result, WireLoss)
    assert math.isclose(result.resistance_ohm, expected_rho * 2.0 / area)


def test_loss_sums_ac_rms_and_dc_contributions() -> None:
    area = conductor_area_m2(0.001)

    result = wire_resistance_and_loss(area, 2.0, 20.0, 3.0, 4.0)

    assert isinstance(result, WireLoss)
    assert math.isclose(result.loss_w, result.resistance_ohm * (9.0 + 16.0))


def test_loss_reports_its_exclusions() -> None:
    result = wire_resistance_and_loss(conductor_area_m2(0.001), 2.0, 20.0, 1.0, 0.0)

    assert isinstance(result, WireLoss)
    joined = " ".join(result.notes)
    assert "DC-resistance wire-loss estimate" in joined
    assert "connector" in joined
    assert "lead" in joined


@pytest.mark.parametrize("temperature", [9.9, 100.1, -40.0, 150.0])
def test_temperature_outside_the_validated_range_is_not_extrapolated(
    temperature: float,
) -> None:
    result = wire_resistance_and_loss(
        conductor_area_m2(0.001), 2.0, temperature, 1.0, 0.0
    )

    assert isinstance(result, PreliminaryValue)
    assert result.code == DiagnosticCode.WIRE_LOSS_TEMPERATURE_OUT_OF_RANGE
    assert "10" in str(result.message)
    assert "100" in str(result.message)


@pytest.mark.parametrize("temperature", [10.0, 100.0])
def test_the_validated_range_is_inclusive(temperature: float) -> None:
    result = wire_resistance_and_loss(
        conductor_area_m2(0.001), 2.0, temperature, 1.0, 0.0
    )

    assert isinstance(result, WireLoss)


def test_missing_wire_length_is_a_geometry_diagnostic() -> None:
    result = wire_resistance_and_loss(conductor_area_m2(0.001), 0.0, 20.0, 1.0, 0.0)

    assert isinstance(result, PreliminaryValue)
    assert result.code == DiagnosticCode.WIRE_LOSS_NO_GEOMETRY
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/simulation/test_winding_estimate.py -q`
Expected: FAIL with `ImportError: cannot import name 'COPPER_RHO_20_OHM_M'`.

- [ ] **Step 3: Implement resistance and loss**

Append to `src/inductor_designer/simulation/winding_estimate.py`:

```python
# Annealed 100% IACS copper, from the US National Bureau of Standards copper
# measurements: https://nvlpubs.nist.gov/nistpubs/bulletin/07/nbsbulletinv7n1p71_A2b.pdf
# The range is the validated linear range, not a convenience clamp: outside it
# resistance and loss are reported unavailable rather than extrapolated.
COPPER_RHO_20_OHM_M = 1.7241e-8
COPPER_ALPHA_20_PER_C = 0.00393
COPPER_MIN_TEMPERATURE_C = 10.0
COPPER_MAX_TEMPERATURE_C = 100.0

WIRE_LOSS_EXCLUSION_NOTE = (
    "DC-resistance wire-loss estimate; excludes skin effect, proximity effect, "
    "eddy-current loss, terminal loss, connector loss, and temperature rise"
)
LEAD_EXCLUSION_NOTE = (
    "wire length is the modeled closed-loop turn length; connectors, external "
    "leads, and terminals are excluded"
)


@dataclass(frozen=True, slots=True)
class WireLoss:
    resistance_ohm: float
    loss_w: float
    notes: tuple[str, ...]


def wire_resistance_and_loss(
    area_m2: float,
    wire_length_m: float,
    winding_temperature_c: float,
    ac_rms_current_a: float,
    dc_current_a: float,
) -> WireLoss | PreliminaryValue:
    if not wire_length_m > 0.0:
        return unavailable(
            DiagnosticCode.WIRE_LOSS_NO_GEOMETRY,
            "Winding geometry produced no modeled wire length, so resistance "
            "and wire loss cannot be estimated.",
        )
    if not (
        COPPER_MIN_TEMPERATURE_C <= winding_temperature_c <= COPPER_MAX_TEMPERATURE_C
    ):
        return unavailable(
            DiagnosticCode.WIRE_LOSS_TEMPERATURE_OUT_OF_RANGE,
            f"Winding temperature {winding_temperature_c:g} C is outside the "
            f"validated copper range {COPPER_MIN_TEMPERATURE_C:g} C through "
            f"{COPPER_MAX_TEMPERATURE_C:g} C; resistance is not extrapolated.",
        )

    rho = COPPER_RHO_20_OHM_M * (
        1.0 + COPPER_ALPHA_20_PER_C * (winding_temperature_c - 20.0)
    )
    resistance = rho * wire_length_m / area_m2
    return WireLoss(
        resistance_ohm=resistance,
        loss_w=resistance * (ac_rms_current_a**2 + dc_current_a**2),
        notes=(WIRE_LOSS_EXCLUSION_NOTE, LEAD_EXCLUSION_NOTE),
    )
```

Add these imports at the top of the module:

```python
from inductor_designer.simulation.preliminary_contracts import (
    DiagnosticCode,
    PreliminaryValue,
    unavailable,
)
```

- [ ] **Step 4: Run the tests and verify GREEN**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/simulation/test_winding_estimate.py -q`
Expected: `15 passed`.

- [ ] **Step 5: Run the gates and commit**

```bash
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy src tools
.venv/Scripts/python.exe tools/check_architecture.py
git add src/inductor_designer/simulation/winding_estimate.py tests/unit/simulation/test_winding_estimate.py
git commit -m "feat(simulation): estimate copper resistance and DC-resistance wire loss"
```

---

### Task 6: Core loss from a loss table or the stored Steinmetz fit

**Files:**
- Create: `src/inductor_designer/simulation/core_loss_estimate.py`
- Test: `tests/unit/simulation/test_core_loss_estimate.py`

**Interfaces:**
- Consumes: Task 1 contracts; Task 3 `FluxDensities`.
- Produces: `core_loss_w(selection, b_ac_peak_t, frequency_hz,
  core_temperature_c, h_dc_a_per_m, core_volume_m3) -> PreliminaryValue`.

Evaluation order from specification section 8, in order:

1. A compatible recorded loss table at the requested frequency, temperature and
   DC-bias condition, interpolating only inside its recorded flux range.
2. Otherwise the stored Steinmetz fit, when the requested frequency and
   `B_AC_peak` lie inside the source-data envelope and every loss series
   supports the requested temperature and DC-bias condition.
3. Otherwise Unavailable.

```text
P_volume = k * frequency^alpha * B_AC_peak^beta
P_core   = P_volume * core_volume
```

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/simulation/test_core_loss_estimate.py`:

```python
from __future__ import annotations

import math

from inductor_designer.simulation.core_loss_estimate import core_loss_w
from inductor_designer.simulation.preliminary_contracts import (
    DiagnosticCode,
    ResultState,
)
from tests.unit.simulation.test_magnetic_estimate import _selection
from inductor_designer.materials.records import (
    CurveConditions,
    CurvePoint,
    PointSeries,
    SeriesKind,
    SteinmetzFit,
)


def _loss_series(
    series_id: str = "loss-100khz",
    frequency_hz: float | None = 100_000.0,
    temperature_c: float | None = 25.0,
    dc_bias_a_per_m: float | None = 0.0,
    points: tuple[tuple[float, float], ...] = ((0.05, 1000.0), (0.1, 4000.0)),
) -> PointSeries:
    return PointSeries(
        series_id=series_id,
        kind=SeriesKind.LOSS_TABLE,
        x_unit="T",
        y_unit="W/m3",
        conditions=CurveConditions(
            frequency_hz=frequency_hz,
            temperature_c=temperature_c,
            dc_bias_a_per_m=dc_bias_a_per_m,
        ),
        points=tuple(CurvePoint(b, loss) for b, loss in points),
        source_filename="loss.csv",
    )


def test_loss_table_is_preferred_and_interpolated_inside_its_range() -> None:
    result = core_loss_w(
        _selection(series=(_loss_series(),)),
        b_ac_peak_t=0.075,
        frequency_hz=100_000.0,
        core_temperature_c=25.0,
        h_dc_a_per_m=0.0,
        core_volume_m3=5.34e-6,
    )

    assert result.state is ResultState.ESTIMATED
    assert result.value is not None
    assert math.isclose(result.value, 2500.0 * 5.34e-6)


def test_flux_beyond_the_loss_table_range_is_not_extrapolated() -> None:
    result = core_loss_w(
        _selection(series=(_loss_series(),)),
        b_ac_peak_t=0.5,
        frequency_hz=100_000.0,
        core_temperature_c=25.0,
        h_dc_a_per_m=0.0,
        core_volume_m3=5.34e-6,
    )

    assert result.code == DiagnosticCode.CORE_LOSS_FLUX_OUTSIDE_LOSS_RANGE


def test_temperature_mismatch_names_the_recorded_temperatures() -> None:
    result = core_loss_w(
        _selection(series=(_loss_series(temperature_c=25.0),)),
        b_ac_peak_t=0.075,
        frequency_hz=100_000.0,
        core_temperature_c=80.0,
        h_dc_a_per_m=0.0,
        core_volume_m3=5.34e-6,
    )

    assert result.code == DiagnosticCode.CORE_LOSS_NO_LOSS_DATA_FOR_TEMPERATURE
    assert "25" in str(result.message)


def test_nonzero_dc_bias_without_supporting_data_is_unavailable() -> None:
    result = core_loss_w(
        _selection(series=(_loss_series(dc_bias_a_per_m=0.0),)),
        b_ac_peak_t=0.075,
        frequency_hz=100_000.0,
        core_temperature_c=25.0,
        h_dc_a_per_m=1800.0,
        core_volume_m3=5.34e-6,
    )

    assert result.code == DiagnosticCode.CORE_LOSS_NO_LOSS_DATA_FOR_DC_BIAS
    assert "1800" in str(result.message)


def test_steinmetz_fit_is_used_when_no_table_matches_the_frequency() -> None:
    selection = _selection(series=(_loss_series(frequency_hz=50_000.0),))
    fitted = replace_steinmetz(selection, SteinmetzFit(2.0, 1.5, 2.0, 0.0, 0.0))

    result = core_loss_w(
        fitted,
        b_ac_peak_t=0.075,
        frequency_hz=50_000.0,
        core_temperature_c=25.0,
        h_dc_a_per_m=0.0,
        core_volume_m3=5.34e-6,
    )

    expected_volume = 2.0 * 50_000.0**1.5 * 0.075**2.0
    assert result.state is ResultState.ESTIMATED
    assert result.value is not None
    assert math.isclose(result.value, expected_volume * 5.34e-6)


def test_frequency_outside_the_fit_envelope_is_refused() -> None:
    selection = _selection(series=(_loss_series(frequency_hz=100_000.0),))
    fitted = replace_steinmetz(selection, SteinmetzFit(2.0, 1.5, 2.0, 0.0, 0.0))

    result = core_loss_w(
        fitted,
        b_ac_peak_t=0.075,
        frequency_hz=1_000_000.0,
        core_temperature_c=25.0,
        h_dc_a_per_m=0.0,
        core_volume_m3=5.34e-6,
    )

    assert result.code == DiagnosticCode.CORE_LOSS_FREQUENCY_OUTSIDE_FIT_ENVELOPE


def test_no_loss_model_at_all_is_unavailable() -> None:
    result = core_loss_w(
        _selection(),
        b_ac_peak_t=0.075,
        frequency_hz=100_000.0,
        core_temperature_c=25.0,
        h_dc_a_per_m=0.0,
        core_volume_m3=5.34e-6,
    )

    assert result.code == DiagnosticCode.CORE_LOSS_NO_LOSS_MODEL


def test_non_positive_frequency_and_volume_are_refused() -> None:
    selection = _selection(series=(_loss_series(),))

    zero_frequency = core_loss_w(
        selection, 0.075, 0.0, 25.0, 0.0, 5.34e-6
    )
    zero_volume = core_loss_w(
        selection, 0.075, 100_000.0, 25.0, 0.0, 0.0
    )

    assert zero_frequency.code == DiagnosticCode.CORE_LOSS_NON_POSITIVE_FREQUENCY
    assert zero_volume.code == DiagnosticCode.CORE_LOSS_NON_POSITIVE_VOLUME
```

Add this helper at the top of the same test file, because a `MaterialRecord` is
frozen and the fixture from Task 3 builds one without a fit:

```python
from dataclasses import replace

from inductor_designer.domain.project import MaterialRevisionSelection
from inductor_designer.materials.records import SteinmetzFit


def replace_steinmetz(
    selection: MaterialRevisionSelection, fit: SteinmetzFit
) -> MaterialRevisionSelection:
    return replace(selection, snapshot=replace(selection.snapshot, steinmetz=fit))
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/simulation/test_core_loss_estimate.py -q`
Expected: FAIL with `ModuleNotFoundError` for
`inductor_designer.simulation.core_loss_estimate`.

- [ ] **Step 3: Implement core loss**

Create `src/inductor_designer/simulation/core_loss_estimate.py`:

```python
"""Core-loss estimate (specification section 8).

No temperature correction, DC-bias correction, waveform correction, frequency
extrapolation, flux-density extrapolation, or material substitution is invented.
"""

from __future__ import annotations

from inductor_designer.domain.project import MaterialRevisionSelection
from inductor_designer.materials.records import PointSeries, SeriesKind
from inductor_designer.simulation.preliminary_contracts import (
    DiagnosticCode,
    PreliminaryValue,
    estimated,
    unavailable,
)

_STEINMETZ_NOTE = (
    "Steinmetz fit evaluated inside its source-data envelope; no temperature, "
    "DC-bias, or waveform correction is applied"
)
_TABLE_NOTE = "interpolated from a recorded loss table at the requested condition"


def _loss_series(selection: MaterialRevisionSelection) -> tuple[PointSeries, ...]:
    return tuple(
        series
        for series in selection.snapshot.series
        if series.kind is SeriesKind.LOSS_TABLE
    )


def _supports_condition(
    series: PointSeries, core_temperature_c: float, h_dc_a_per_m: float
) -> bool:
    if series.conditions.temperature_c != core_temperature_c:
        return False
    recorded_bias = series.conditions.dc_bias_a_per_m
    return recorded_bias is not None and recorded_bias == h_dc_a_per_m


def _interpolate_loss(series: PointSeries, b_ac_peak_t: float) -> float | None:
    points = sorted(series.points, key=lambda point: point.x)
    if not points or b_ac_peak_t < points[0].x or b_ac_peak_t > points[-1].x:
        return None
    previous = points[0]
    for point in points:
        if point.x == b_ac_peak_t:
            return point.y
        if point.x > b_ac_peak_t:
            span = point.x - previous.x
            if span <= 0.0:
                return point.y
            fraction = (b_ac_peak_t - previous.x) / span
            return previous.y + fraction * (point.y - previous.y)
        previous = point
    return points[-1].y


def core_loss_w(
    selection: MaterialRevisionSelection,
    b_ac_peak_t: float,
    frequency_hz: float,
    core_temperature_c: float,
    h_dc_a_per_m: float,
    core_volume_m3: float,
) -> PreliminaryValue:
    if not frequency_hz > 0.0:
        return unavailable(
            DiagnosticCode.CORE_LOSS_NON_POSITIVE_FREQUENCY,
            f"Core loss requires a positive frequency; got {frequency_hz:g} Hz.",
        )
    if not core_volume_m3 > 0.0:
        return unavailable(
            DiagnosticCode.CORE_LOSS_NON_POSITIVE_VOLUME,
            f"Core loss requires a positive core volume; got {core_volume_m3:g} m3.",
        )

    series = _loss_series(selection)
    if not series:
        return unavailable(
            DiagnosticCode.CORE_LOSS_NO_LOSS_MODEL,
            "The selected material revision has no loss table and no Steinmetz "
            "fit, so core loss cannot be estimated.",
        )

    supported = [
        item for item in series if _supports_condition(item, core_temperature_c, h_dc_a_per_m)
    ]
    if not supported:
        temperatures = sorted(
            {
                item.conditions.temperature_c
                for item in series
                if item.conditions.temperature_c is not None
            }
        )
        biases = sorted(
            {
                item.conditions.dc_bias_a_per_m
                for item in series
                if item.conditions.dc_bias_a_per_m is not None
            }
        )
        if core_temperature_c not in temperatures:
            recorded = ", ".join(f"{value:g} C" for value in temperatures)
            return unavailable(
                DiagnosticCode.CORE_LOSS_NO_LOSS_DATA_FOR_TEMPERATURE,
                f"No loss data recorded at {core_temperature_c:g} C; "
                f"available: {recorded}.",
            )
        recorded_bias = ", ".join(f"{value:g} A/m" for value in biases)
        return unavailable(
            DiagnosticCode.CORE_LOSS_NO_LOSS_DATA_FOR_DC_BIAS,
            f"No loss data recorded at {h_dc_a_per_m:g} A/m DC bias; "
            f"recorded bias: {recorded_bias}.",
        )

    exact = [
        item for item in supported if item.conditions.frequency_hz == frequency_hz
    ]
    if exact:
        volumetric = _interpolate_loss(exact[0], b_ac_peak_t)
        if volumetric is None:
            lowest = min(point.x for point in exact[0].points)
            highest = max(point.x for point in exact[0].points)
            return unavailable(
                DiagnosticCode.CORE_LOSS_FLUX_OUTSIDE_LOSS_RANGE,
                f"AC flux density {b_ac_peak_t:g} T is outside the recorded "
                f"range of series {exact[0].series_id} ({lowest:g} to "
                f"{highest:g} T); extrapolation is not performed.",
            )
        return estimated(volumetric * core_volume_m3, notes=(_TABLE_NOTE,))

    fit = selection.snapshot.steinmetz
    if fit is None:
        return unavailable(
            DiagnosticCode.CORE_LOSS_NO_LOSS_MODEL,
            f"No loss table recorded at {frequency_hz:g} Hz and no Steinmetz "
            "fit is stored on the selected revision.",
        )

    frequencies = [
        item.conditions.frequency_hz
        for item in supported
        if item.conditions.frequency_hz is not None
    ]
    if not frequencies or not min(frequencies) <= frequency_hz <= max(frequencies):
        envelope = (
            f"{min(frequencies):g} to {max(frequencies):g} Hz"
            if frequencies
            else "unknown"
        )
        return unavailable(
            DiagnosticCode.CORE_LOSS_FREQUENCY_OUTSIDE_FIT_ENVELOPE,
            f"Frequency {frequency_hz:g} Hz is outside the fit's source-data "
            f"envelope ({envelope}); the fit is not extrapolated.",
        )

    flux_values = [point.x for item in supported for point in item.points]
    if flux_values and not min(flux_values) <= b_ac_peak_t <= max(flux_values):
        return unavailable(
            DiagnosticCode.CORE_LOSS_FLUX_OUTSIDE_LOSS_RANGE,
            f"AC flux density {b_ac_peak_t:g} T is outside the fit's source-data "
            f"range ({min(flux_values):g} to {max(flux_values):g} T).",
        )

    volumetric = fit.k * frequency_hz**fit.alpha * b_ac_peak_t**fit.beta
    return estimated(volumetric * core_volume_m3, notes=(_STEINMETZ_NOTE,))
```

- [ ] **Step 4: Run the tests and verify GREEN**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/simulation/test_core_loss_estimate.py -q`
Expected: `8 passed`.

- [ ] **Step 5: Run the gates and commit**

```bash
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy src tools
.venv/Scripts/python.exe tools/check_architecture.py
git add src/inductor_designer/simulation/core_loss_estimate.py tests/unit/simulation/test_core_loss_estimate.py
git commit -m "feat(simulation): estimate core loss from loss tables or a stored fit"
```

---

### Task 7: Compose one preliminary result

**Files:**
- Create: `src/inductor_designer/simulation/preliminary.py`
- Test: `tests/unit/simulation/test_preliminary.py`

**Interfaces:**
- Consumes: Tasks 1–6.
- Produces: `PreliminaryRequest`, `WindingPreliminary`, `CorePreliminary`,
  `PreliminaryTotals`, `PreliminaryResult`, and
  `estimate_preliminary(request) -> PreliminaryResult`.

`PreliminaryRequest` fields, all supplied by the caller so this module needs no
repository or catalog access:

```python
project: InductorProject
core_record: CoreRecord | None
conductors_by_winding: Mapping[str, ConductorRecord]
turns_by_winding: Mapping[str, int]
packings_by_winding: Mapping[str, PackedWinding]
```

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/simulation/test_preliminary.py`:

```python
from __future__ import annotations

from dataclasses import replace

from inductor_designer.simulation.preliminary import (
    PreliminaryRequest,
    PreliminaryResult,
    estimate_preliminary,
)
from inductor_designer.simulation.preliminary_contracts import (
    DiagnosticCode,
    ResultState,
)


def test_a_missing_core_makes_only_core_quantities_unavailable(
    sample_request: PreliminaryRequest,
) -> None:
    request = replace(sample_request, core_record=None)

    result = estimate_preliminary(request)

    assert isinstance(result, PreliminaryResult)
    assert result.core.b_dc.code == DiagnosticCode.FLUX_DENSITY_NO_CORE_SELECTED
    assert result.core.core_loss.state is ResultState.UNAVAILABLE
    # windings are independent of the core selection
    assert result.windings[0].j_ac_rms.state is ResultState.ESTIMATED
    assert result.windings[0].wire_loss.state is ResultState.ESTIMATED


def test_total_wire_loss_sums_available_windings(
    sample_request: PreliminaryRequest,
) -> None:
    result = estimate_preliminary(sample_request)

    expected = sum(
        winding.wire_loss.value or 0.0
        for winding in result.windings
        if winding.wire_loss.state is ResultState.ESTIMATED
    )
    assert result.totals.total_wire_loss.state is ResultState.ESTIMATED
    assert result.totals.total_wire_loss.value == expected


def test_total_loss_is_unavailable_unless_both_components_exist(
    sample_request: PreliminaryRequest,
) -> None:
    result = estimate_preliminary(replace(sample_request, core_record=None))

    assert result.totals.total_loss.state is ResultState.UNAVAILABLE
    assert result.totals.total_loss.code == DiagnosticCode.TOTAL_LOSS_INCOMPLETE


def test_every_winding_row_is_reported_even_without_a_conductor(
    sample_request: PreliminaryRequest,
) -> None:
    request = replace(sample_request, conductors_by_winding={})

    result = estimate_preliminary(request)

    assert len(result.windings) == len(sample_request.project.design.windings)
    assert result.windings[0].j_ac_rms.code == DiagnosticCode.CURRENT_DENSITY_NO_CONDUCTOR


def test_the_result_records_the_pinned_revision_and_is_deterministic(
    sample_request: PreliminaryRequest,
) -> None:
    first = estimate_preliminary(sample_request)
    second = estimate_preliminary(sample_request)

    assert first == second
    assert first.material_revision_id == "0123456789ab"
```

Create the fixture in `tests/unit/simulation/conftest.py`:

```python
from __future__ import annotations

import pytest

from inductor_designer.domain.catalog_records import ConductorRecord, CoreRecord
from inductor_designer.domain.project import (
    Design,
    InductorProject,
    OperatingPoint,
    WindingOperatingPoint,
)
from inductor_designer.domain.winding import CurrentDirection, WindingDefinition
from inductor_designer.geometry.packing import PackedWinding
from inductor_designer.simulation.preliminary import PreliminaryRequest
from tests.unit.simulation.test_magnetic_estimate import _bh_series, _selection


@pytest.fixture
def sample_request() -> PreliminaryRequest:
    """Two forward windings of 10 turns on a C058071A2-sized core at 100 kHz.

    The B-H series is recorded at 25 C, matching the default core temperature,
    so flux density is Estimated. No loss series is present, so core loss is
    Unavailable — the tests that need core loss add a series explicitly.
    """
    selection = _selection(series=(_bh_series(),), bh_series_id="bh-25c")
    core_record = CoreRecord(
        part_number="C058071A2",
        manufacturer="Magnetics",
        family="powder-toroid",
        material=selection.ref,
        effective_area_m2=6.56e-5,
        path_length_m=0.0814,
        volume_m3=5.34e-6,
        al_value_nh=61.0,
    )
    conductor = ConductorRecord(
        designation="AWG 18",
        standard="AWG",
        bare_diameter_m=0.001024,
    )
    windings = tuple(
        WindingDefinition(winding_id=winding_id, turns=10, conductor="AWG 18")
        for winding_id in ("w1", "w2")
    )
    operating_point = OperatingPoint(
        frequency_hz=100_000.0,
        winding_temperature_c=20.0,
        core_temperature_c=25.0,
        windings=tuple(
            WindingOperatingPoint(
                winding_id=winding_id,
                ac_rms_current_a=2.0,
                ac_phase_deg=0.0,
                dc_current_a=0.0,
                current_direction=CurrentDirection.FORWARD,
            )
            for winding_id in ("w1", "w2")
        ),
    )
    project = InductorProject(
        design=Design(
            core=None,
            windings=windings,
            core_material=selection,
            manual_material_compatibility_acknowledged=False,
        ),
        operating_point=operating_point,
    )
    return PreliminaryRequest(
        project=project,
        core_record=core_record,
        conductors_by_winding={"w1": conductor, "w2": conductor},
        turns_by_winding={"w1": 10, "w2": 10},
        packings_by_winding={
            winding_id: PackedWinding(
                winding_id=winding_id,
                insulated_diameter_m=0.001094,
                sector_deg=150.0,
                start_deg=0.0,
                layers=(),
                lead_in_deg=0.0,
                lead_out_deg=0.0,
                wire_length_m=0.4,
            )
            for winding_id in ("w1", "w2")
        },
    )
```

**Before writing this fixture, run**
`.venv/Scripts/python.exe -c "import inspect; from inductor_designer.domain import catalog_records, project, winding; print(inspect.signature(catalog_records.CoreRecord)); print(inspect.signature(catalog_records.ConductorRecord)); print(inspect.signature(winding.WindingDefinition)); print(inspect.signature(project.InductorProject))"`
and correct any constructor argument that has drifted. The fixture must
construct real objects; adjust names to the live signatures rather than editing
the domain types to fit this plan.

- [ ] **Step 2: Run the tests and verify RED**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/simulation/test_preliminary.py -q`
Expected: FAIL with `ModuleNotFoundError` for
`inductor_designer.simulation.preliminary`.

- [ ] **Step 3: Implement composition**

Create `src/inductor_designer/simulation/preliminary.py`:

```python
"""One preliminary result per project (specification sections 4.3 and 5).

Each quantity is evaluated independently: a missing loss curve makes core loss
unavailable while flux density, current density, and wire loss stay estimated.
Results are derived data and are never persisted into the Project document.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from inductor_designer.domain.catalog_records import ConductorRecord, CoreRecord
from inductor_designer.domain.project import InductorProject
from inductor_designer.geometry.packing import PackedWinding
from inductor_designer.simulation.core_loss_estimate import core_loss_w
from inductor_designer.simulation.magnetic_estimate import (
    FieldStrengths,
    FluxDensities,
    field_strengths,
    flux_densities,
)
from inductor_designer.simulation.preliminary_contracts import (
    DiagnosticCode,
    PreliminaryValue,
    ResultState,
    estimated,
    unavailable,
)
from inductor_designer.simulation.winding_estimate import (
    WireLoss,
    conductor_area_m2,
    current_densities,
    wire_resistance_and_loss,
)


@dataclass(frozen=True, slots=True)
class PreliminaryRequest:
    """Everything the estimator needs, already resolved by the caller.

    Taking records rather than repositories keeps this module free of SQLite and
    the filesystem, and makes every test constructible without I/O.
    """

    project: InductorProject
    core_record: CoreRecord | None
    conductors_by_winding: Mapping[str, ConductorRecord]
    turns_by_winding: Mapping[str, int]
    packings_by_winding: Mapping[str, PackedWinding]


@dataclass(frozen=True, slots=True)
class WindingPreliminary:
    winding_id: str
    conductor_area: PreliminaryValue
    j_ac_rms: PreliminaryValue
    j_ac_peak: PreliminaryValue
    j_dc: PreliminaryValue
    wire_length: PreliminaryValue
    resistance: PreliminaryValue
    wire_loss: PreliminaryValue


@dataclass(frozen=True, slots=True)
class CorePreliminary:
    b_dc: PreliminaryValue
    b_min: PreliminaryValue
    b_max: PreliminaryValue
    b_ac_peak: PreliminaryValue
    b_peak_magnitude: PreliminaryValue
    core_loss: PreliminaryValue


@dataclass(frozen=True, slots=True)
class PreliminaryTotals:
    total_wire_loss: PreliminaryValue
    core_loss: PreliminaryValue
    total_loss: PreliminaryValue


@dataclass(frozen=True, slots=True)
class PreliminaryResult:
    core: CorePreliminary
    windings: tuple[WindingPreliminary, ...]
    totals: PreliminaryTotals
    material_revision_id: str | None
    bh_series_id: str | None
    notes: tuple[str, ...] = field(default_factory=tuple)


def _core_all(reason: PreliminaryValue) -> CorePreliminary:
    """One reason, reported identically for every core quantity."""
    return CorePreliminary(
        b_dc=reason,
        b_min=reason,
        b_max=reason,
        b_ac_peak=reason,
        b_peak_magnitude=reason,
        core_loss=reason,
    )


def _core_estimates(
    request: PreliminaryRequest,
    fields: FieldStrengths,
    densities: FluxDensities,
    core_record: CoreRecord,
) -> CorePreliminary:
    material = request.project.design.core_material
    if material is None:  # guarded by the caller
        raise AssertionError("_core_estimates requires a selected material")
    operating_point = request.project.operating_point
    loss = core_loss_w(
        material,
        b_ac_peak_t=densities.b_ac_peak_t,
        frequency_hz=operating_point.frequency_hz,
        core_temperature_c=operating_point.core_temperature_c,
        h_dc_a_per_m=fields.h_dc_a_per_m,
        core_volume_m3=core_record.volume_m3,
    )
    return CorePreliminary(
        b_dc=estimated(densities.b_dc_t, densities.notes),
        b_min=estimated(densities.b_min_t, densities.notes),
        b_max=estimated(densities.b_max_t, densities.notes),
        b_ac_peak=estimated(densities.b_ac_peak_t, densities.notes),
        b_peak_magnitude=estimated(densities.b_peak_magnitude_t, densities.notes),
        core_loss=loss,
    )


def _winding_row(request: PreliminaryRequest, winding_id: str) -> WindingPreliminary:
    conductor = request.conductors_by_winding.get(winding_id)
    if conductor is None:
        reason = unavailable(
            DiagnosticCode.CURRENT_DENSITY_NO_CONDUCTOR,
            f"Winding {winding_id} has no resolved conductor record, so its "
            "copper area, current densities, and wire loss cannot be estimated.",
        )
        return WindingPreliminary(
            winding_id=winding_id,
            conductor_area=reason,
            j_ac_rms=reason,
            j_ac_peak=reason,
            j_dc=reason,
            wire_length=reason,
            resistance=reason,
            wire_loss=reason,
        )

    area = conductor_area_m2(conductor.bare_diameter_m)
    excitation = next(
        (
            item
            for item in request.project.operating_point.windings
            if item.winding_id == winding_id
        ),
        None,
    )
    ac_rms = excitation.ac_rms_current_a if excitation is not None else 0.0
    dc = excitation.dc_current_a if excitation is not None else 0.0
    densities = current_densities(area, ac_rms, dc)

    packing = request.packings_by_winding.get(winding_id)
    wire_length_m = packing.wire_length_m if packing is not None else 0.0
    loss = wire_resistance_and_loss(
        area,
        wire_length_m,
        request.project.operating_point.winding_temperature_c,
        ac_rms,
        dc,
    )
    if isinstance(loss, WireLoss):
        resistance = estimated(loss.resistance_ohm, loss.notes)
        wire_loss = estimated(loss.loss_w, loss.notes)
        length = estimated(wire_length_m, loss.notes)
    else:
        resistance = loss
        wire_loss = loss
        length = loss

    return WindingPreliminary(
        winding_id=winding_id,
        conductor_area=estimated(area),
        j_ac_rms=estimated(densities.j_ac_rms_a_per_m2),
        j_ac_peak=estimated(densities.j_ac_peak_a_per_m2),
        j_dc=estimated(densities.j_dc_a_per_m2),
        wire_length=length,
        resistance=resistance,
        wire_loss=wire_loss,
    )


def _totals(
    windings: tuple[WindingPreliminary, ...], core_loss: PreliminaryValue
) -> PreliminaryTotals:
    available = [
        row.wire_loss.value
        for row in windings
        if row.wire_loss.state is ResultState.ESTIMATED
        and row.wire_loss.value is not None
    ]
    if available:
        total_wire = estimated(sum(available))
    else:
        total_wire = unavailable(
            DiagnosticCode.TOTAL_LOSS_INCOMPLETE,
            "No winding produced an estimated wire loss, so no partial total is "
            "reported.",
        )

    if (
        total_wire.state is ResultState.ESTIMATED
        and core_loss.state is ResultState.ESTIMATED
        and total_wire.value is not None
        and core_loss.value is not None
    ):
        total = estimated(total_wire.value + core_loss.value)
    else:
        total = unavailable(
            DiagnosticCode.TOTAL_LOSS_INCOMPLETE,
            "Total preliminary loss requires both wire loss and core loss; one "
            "component is unavailable, so no partial total is reported.",
        )
    return PreliminaryTotals(
        total_wire_loss=total_wire, core_loss=core_loss, total_loss=total
    )


def estimate_preliminary(request: PreliminaryRequest) -> PreliminaryResult:
    design = request.project.design
    material = design.core_material

    if request.core_record is None:
        core = _core_all(
            unavailable(
                DiagnosticCode.FLUX_DENSITY_NO_CORE_SELECTED,
                "No core is selected, so core flux density and core loss cannot "
                "be estimated.",
            )
        )
    elif material is None:
        core = _core_all(
            unavailable(
                DiagnosticCode.FLUX_DENSITY_NO_MATERIAL_SELECTED,
                "No core material revision is selected, so core flux density "
                "and core loss cannot be estimated.",
            )
        )
    else:
        fields = field_strengths(
            request.project.operating_point,
            request.turns_by_winding,
            request.core_record.path_length_m,
        )
        if isinstance(fields, PreliminaryValue):
            core = _core_all(fields)
        else:
            densities = flux_densities(
                material,
                fields,
                request.project.operating_point.core_temperature_c,
            )
            if isinstance(densities, PreliminaryValue):
                core = _core_all(densities)
            else:
                core = _core_estimates(request, fields, densities, request.core_record)

    windings = tuple(
        _winding_row(request, definition.winding_id) for definition in design.windings
    )

    notes: list[str] = []
    for value in (core.b_dc, core.core_loss, *(row.wire_loss for row in windings)):
        for note in value.notes:
            if note not in notes:
                notes.append(note)

    return PreliminaryResult(
        core=core,
        windings=windings,
        totals=_totals(windings, core.core_loss),
        material_revision_id=material.revision_id if material is not None else None,
        bh_series_id=material.bh_series_id if material is not None else None,
        notes=tuple(notes),
    )
```

`WindingDefinition` must expose `winding_id`. Confirm the live signatures
before writing this file:

```bash
.venv/Scripts/python.exe -c "import inspect; from inductor_designer.domain import catalog_records, project, winding; print(inspect.signature(catalog_records.CoreRecord)); print(inspect.signature(catalog_records.ConductorRecord)); print(inspect.signature(winding.WindingDefinition)); print(inspect.signature(project.InductorProject))"
```

Use the live attribute names if any have drifted; adjust this code rather
than the domain types.

- [ ] **Step 4: Run the tests and verify GREEN**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/simulation/test_preliminary.py -q`
Expected: `5 passed`.

- [ ] **Step 5: Run the gates and commit**

```bash
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy src tools
.venv/Scripts/python.exe tools/check_architecture.py
git add src/inductor_designer/simulation/preliminary.py tests/unit/simulation/test_preliminary.py tests/unit/simulation/conftest.py
git commit -m "feat(simulation): compose one preliminary result per project"
```

---

### Task 8: Exit criterion and boundary proof

**Files:**
- Create: `tests/integration/test_preliminary_estimator.py`
- Modify: `docs/development/ROADMAP.md`
- Modify: `docs/superpowers/plans/README.md`

**Interfaces:**
- Consumes: Task 7 `estimate_preliminary`.
- Produces: the M7a acceptance evidence.

- [ ] **Step 1: Write the exit-criterion test**

Create `tests/integration/test_preliminary_estimator.py`. It uses the real
overlay revision and the real catalog record, so it proves the estimator against
shipped data rather than a fixture:

```python
from __future__ import annotations

import sys
from pathlib import Path

from inductor_designer.adapters.materials.overlay_repository import (
    FileOverlayMaterialRepository,
)
from inductor_designer.domain.project import (
    Design,
    InductorProject,
    MaterialRevisionSelection,
    OperatingPoint,
    WindingOperatingPoint,
)
from inductor_designer.domain.winding import CurrentDirection, WindingDefinition
from inductor_designer.geometry.packing import PackedWinding
from inductor_designer.materials.identity import MaterialRef
from inductor_designer.simulation.preliminary import (
    PreliminaryRequest,
    estimate_preliminary,
)
from inductor_designer.simulation.preliminary_contracts import (
    DiagnosticCode,
    ResultState,
)
from tools.build_catalog import build

ROOT = Path(__file__).resolve().parents[2]
REF = MaterialRef("Magnetics", "High Flux", "60")


def _real_project_request(tmp_path: Path) -> PreliminaryRequest:
    """The M5a validation material and core, with 5 A DC per winding."""
    from inductor_designer.adapters.catalog.sqlite_repository import (
        SqliteCatalogRepository,
    )

    index = tmp_path / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    catalog = SqliteCatalogRepository(index)
    core_record = catalog.core("C058071A2")
    conductor = catalog.conductor("AWG 18")

    repository = FileOverlayMaterialRepository(ROOT / "materials-overlay")
    revision_id = repository.list_revisions(REF)[0]
    snapshot = repository.get(REF, revision_id)
    selection = MaterialRevisionSelection(
        ref=REF,
        revision_id=revision_id,
        snapshot=snapshot,
        bh_series_id="bh-25c",
    )

    winding_ids = ("w1", "w2")
    project = InductorProject(
        design=Design(
            core=None,
            windings=tuple(
                WindingDefinition(
                    winding_id=winding_id, turns=10, conductor="AWG 18"
                )
                for winding_id in winding_ids
            ),
            core_material=selection,
            manual_material_compatibility_acknowledged=False,
        ),
        operating_point=OperatingPoint(
            frequency_hz=100_000.0,
            winding_temperature_c=20.0,
            core_temperature_c=25.0,
            windings=tuple(
                WindingOperatingPoint(
                    winding_id=winding_id,
                    ac_rms_current_a=2.0,
                    ac_phase_deg=0.0,
                    dc_current_a=5.0,
                    current_direction=CurrentDirection.FORWARD,
                )
                for winding_id in winding_ids
            ),
        ),
    )
    return PreliminaryRequest(
        project=project,
        core_record=core_record,
        conductors_by_winding={winding_id: conductor for winding_id in winding_ids},
        turns_by_winding={winding_id: 10 for winding_id in winding_ids},
        packings_by_winding={
            winding_id: PackedWinding(
                winding_id=winding_id,
                insulated_diameter_m=0.001094,
                sector_deg=150.0,
                start_deg=0.0,
                layers=(),
                lead_in_deg=0.0,
                lead_out_deg=0.0,
                wire_length_m=0.4,
            )
            for winding_id in winding_ids
        },
    )


def test_preliminary_estimates_reproduce_without_qt_maxwell_or_femm(
    tmp_path: Path,
) -> None:
    """Specification acceptance criterion 8."""
    result = estimate_preliminary(_real_project_request(tmp_path))

    assert result.core.b_peak_magnitude.state is ResultState.ESTIMATED
    assert result.windings[0].j_ac_rms.state is ResultState.ESTIMATED
    assert result.windings[0].wire_loss.state is ResultState.ESTIMATED
    # 5 A DC with loss data recorded only at 0 A/m: core loss must be refused,
    # never invented by ignoring the DC-bias condition.
    assert (
        result.core.core_loss.code
        == DiagnosticCode.CORE_LOSS_NO_LOSS_DATA_FOR_DC_BIAS
    )
    assert result.totals.total_wire_loss.state is ResultState.ESTIMATED
    assert result.totals.total_loss.code == DiagnosticCode.TOTAL_LOSS_INCOMPLETE
    assert result.material_revision_id == revision_for_assertions(result)
    # The estimator itself must not drag in Qt or a solver.
    for forbidden in ("PySide6", "ansys.aedt.core", "femm"):
        assert forbidden not in sys.modules


def revision_for_assertions(result: object) -> str:
    """The pinned revision is whatever the overlay currently holds."""
    repository = FileOverlayMaterialRepository(ROOT / "materials-overlay")
    return repository.list_revisions(REF)[0]
```

Confirm the catalog accessor names before writing this file; `core(...)` and
`conductor(...)` are the expected `SqliteCatalogRepository` lookups:

```bash
.venv/Scripts/python.exe -c "import inspect; from inductor_designer.adapters.catalog.sqlite_repository import SqliteCatalogRepository; print([name for name in dir(SqliteCatalogRepository) if not name.startswith('_')])"
```

- [ ] **Step 2: Run it and verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/integration/test_preliminary_estimator.py -q`
Expected: `1 passed`. If `PySide6` is already imported by an earlier test in the
same session, run this file alone — the assertion is about the estimator's own
imports.

- [ ] **Step 3: Run the complete gate set**

```bash
.venv/Scripts/python.exe -m pytest tests -q -m "not aedt and not femm"
QT_QPA_PLATFORM=offscreen QSG_RHI_BACKEND=software .venv/Scripts/python.exe -m pytest tests -q -m ui
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy src tools
.venv/Scripts/python.exe tools/check_architecture.py
git diff --check
```

Expected: every command exits 0, with no fewer tests passing than the 821
non-solver and 37 UI tests recorded at M6 acceptance.

- [ ] **Step 4: Record acceptance and commit**

Add an M7a section to `docs/development/ROADMAP.md` and update the M7 row in
`docs/superpowers/plans/README.md` to note that M7a is complete and that M7b
(project-local run artifacts) is the next plan. State the exact test counts and
that no live solver was required.

```bash
git add tests/integration/test_preliminary_estimator.py docs/development/ROADMAP.md docs/superpowers/plans/README.md
git commit -m "test(simulation): prove the preliminary exit criterion without solvers"
```

---

## Requirement coverage

| Specification requirement | Task |
| --- | --- |
| §5 estimator layering, no Qt/PyAEDT/FEMM/SQLite/OS imports | 1–7, proven in 8 |
| §5 one immutable result, per-quantity independence | 1, 7 |
| §6 AC phasor summation with phase and direction | 2 |
| §6 separate DC ampere-turn summation | 2 |
| §6 `H_AC_peak`, `H_DC`, `H_min`, `H_max` | 2 |
| §6 B-H interpolation, no extrapolation | 3 |
| §6 odd symmetry for negative H, reported | 3 |
| §6 temperature support, naming available temperatures | 3 |
| §6 linear permeability fallback with its label | 3 |
| §6 lumped-estimate caveat | 3 module docstring |
| §7 conductor area, `J_AC_RMS`, `J_AC_peak`, `J_DC` | 4 |
| §7 copper constants and validated range | 5 |
| §7 resistance, mixed AC/DC wire loss | 5 |
| §7 connector and lead exclusion, always visible | 5 |
| §7 per-winding losses may be summed | 7 |
| §8 loss table preferred, interpolated in range | 6 |
| §8 Steinmetz fallback inside the source envelope | 6 |
| §8 DC bias without data makes core loss unavailable | 6, 8 |
| §8 no invented corrections | 6 |
| §9 stable diagnostic code plus English text | 1, all |
| §9 partial availability | 7 |
| §11.8 deterministic reproduction without Qt/Maxwell/FEMM | 8 |

Requirements deliberately **not** in this plan, with their owner:

| Requirement | Owner |
| --- | --- |
| §4.1–4.2 Core & Material and Windings screens, bidirectional filtering, validators | M7c |
| §4.3 Preliminary screen presentation and live refresh | M7c |
| §4.4 Simulation/Review screens, `Show solver window` | M7b and M7c |
| ADR 0007 run directories, `run-id`, post-generation actions | M7b |
| §4.1 separate Material Studio window and library refresh | M7c |

## Self-review notes

- `_interpolate` and `_interpolate_loss` are deliberately separate: the B-H one
  is odd-symmetric about the origin and refuses only magnitudes above the
  recorded maximum, while the loss one has no symmetry and refuses values below
  the recorded minimum as well.
- Task 3 keeps `flux_densities` in the same module as `field_strengths` because
  they share the odd-symmetry assumption and are always used together.
- `PreliminaryRequest` takes resolved records rather than repositories, which is
  what keeps `simulation/` free of SQLite and the filesystem and makes every test
  above constructible without I/O.
- The M5a sample material produces an Unavailable core loss under DC bias. That
  is asserted in Task 8 on purpose so a future change that silently starts
  interpolating DC-bias loss fails the exit criterion.
