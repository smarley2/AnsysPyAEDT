# Preliminary Inductance and A_L Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Report inductance, effective `A_L`, the catalog `A_L` check, effective
permeability, stored energy, and the effective-core-geometry echo on the
Preliminary screen.

**Architecture:** All new physics lives in one new pure module,
`simulation/inductance_estimate.py`, alongside the existing `magnetic_estimate`,
`winding_estimate`, and `core_loss_estimate` modules. It consumes the
`FieldStrengths` and `FluxDensities` the estimator already computes, so nothing
recomputes a field. `simulation/preliminary.py` wires it into `CorePreliminary`
and `WindingPreliminary`; `ui/preliminary_rows.py` does every unit conversion;
QML renders and computes nothing.

**Tech Stack:** Python 3.12, PySide6/QML, pytest, ruff, mypy.

**Design:**
[2026-08-10 Preliminary inductance and A_L check](../specs/2026-08-10-preliminary-inductance-and-al-check-design.md)

## Global Constraints

- English for code, tests, docs, UI copy, logs, commits.
- `domain`, `geometry`, `materials`, and `simulation` import no PyAEDT, Qt,
  SQLite, or OS APIs. `simulation/inductance_estimate.py` imports only
  `math`, `dataclasses`, and `simulation.preliminary_contracts` /
  `simulation.magnetic_estimate`.
- ruff `line-length = 100`.
- Tests are written and seen to fail before implementation (`AGENTS.md`).
- Diagnostic codes are stable `<quantity>.<reason>` strings. Never reuse or
  repurpose one; add a new code instead.
- Preliminary starts no solver and persists nothing.
- `μ₀ = 4e-7 * math.pi`, imported as `MU_0` from
  `simulation.magnetic_estimate`. Do not redefine it.

**This worktree needs `PYTHONPATH` set, or the editable install resolves
`inductor_designer` to the main checkout instead of this worktree.** Run this
once per shell before any test command below:

```bash
cd C:/Work/git/AnsysPyAEDT/.worktrees/preliminary-inductance && export PY="C:/Work/git/AnsysPyAEDT/.venv/Scripts/python.exe" && export PYTHONPATH="$PWD/src"
```

Baseline at plan time: 1161 passed, 7 skipped.

---

### Task 1: Carry effective area and catalog A_L to the estimator

`CoreMagneticProperties` is the only core data the estimator sees. It carries
path length and volume; `A_L` needs the effective area too, and the check needs
the manufacturer's `A_L`. Both new fields are required — no defaults — so that
a caller that forgets one fails loudly at construction instead of silently
producing an Unavailable row.

**Files:**
- Modify: `src/inductor_designer/simulation/preliminary_contracts.py:65-77`
- Modify: `src/inductor_designer/application/services/preliminary_inputs.py:39-60`
- Test: `tests/unit/simulation/test_preliminary_contracts.py:74-89`
- Test: `tests/unit/application/test_preliminary_inputs.py`
- Modify (construction sites that must keep compiling):
  `tests/unit/simulation/conftest.py:133-136`,
  `tests/integration/test_preliminary_estimator.py:123-126`

**Interfaces:**
- Produces: `CoreMagneticProperties(path_length_m: float, volume_m3: float,
  effective_area_m2: float, al_value_nh: float | None,
  notes: tuple[str, ...] = ())`. `al_value_nh is None` means "this core has no
  manufacturer inductance factor" and is the Manual-core case.

- [ ] **Step 1: Write the failing tests**

In `tests/unit/simulation/test_preliminary_contracts.py`, replace the body of
`test_core_magnetic_properties_allow_every_number_including_non_finite` with:

```python
    zero = CoreMagneticProperties(
        path_length_m=0.0, volume_m3=0.0, effective_area_m2=0.0, al_value_nh=None
    )
    overflowed = CoreMagneticProperties(
        path_length_m=float("inf"),
        volume_m3=float("inf"),
        effective_area_m2=float("inf"),
        al_value_nh=61.0,
    )

    assert zero.path_length_m == 0.0
    assert zero.effective_area_m2 == 0.0
    assert zero.al_value_nh is None
    assert zero.notes == ()
    assert overflowed.volume_m3 == float("inf")
    assert overflowed.effective_area_m2 == float("inf")
```

In `tests/unit/application/test_preliminary_inputs.py`, add to
`test_catalog_core_uses_the_manufacturer_effective_values`:

```python
    assert properties.effective_area_m2 == record.effective_area_m2
    assert properties.al_value_nh == record.al_value_nh
```

and add these two tests:

```python
def test_manual_core_computes_its_area_and_has_no_catalog_al() -> None:
    """A Manual core has no manufacturer inductance factor, so the A_L check
    has no reference. The area is the same rectangular cross-section already
    described by MANUAL_CORE_PATH_NOTE.
    """
    selection = ManualCoreSelection(
        outer_diameter_m=0.0272,
        inner_diameter_m=0.0138,
        height_m=0.0112,
        corner_radius_m=0.0,
    )

    properties = core_magnetic_properties(selection)

    assert properties is not None
    assert properties.effective_area_m2 == ((0.0272 - 0.0138) / 2.0) * 0.0112
    assert properties.al_value_nh is None


def test_catalog_core_with_dimension_overrides_keeps_the_catalog_area_and_al() -> None:
    record = make_core()
    selection = CatalogCoreSelection(
        record.part_number,
        record,
        (CoreOverride("outer_diameter_m", 0.03, "measured"),),
    )

    properties = core_magnetic_properties(selection)

    assert properties is not None
    assert properties.effective_area_m2 == record.effective_area_m2
    assert properties.al_value_nh == record.al_value_nh
    assert properties.notes == (CATALOG_OVERRIDE_NOTE,)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
$PY -m pytest tests/unit/simulation/test_preliminary_contracts.py tests/unit/application/test_preliminary_inputs.py -q
```

Expected: FAIL — `TypeError: CoreMagneticProperties.__init__() got an
unexpected keyword argument 'effective_area_m2'`.

- [ ] **Step 3: Extend the contract**

In `src/inductor_designer/simulation/preliminary_contracts.py`, replace the
`CoreMagneticProperties` docstring and fields with:

```python
@dataclass(frozen=True, slots=True)
class CoreMagneticProperties:
    """The core properties the estimator reads, and how they were obtained.

    A catalog core supplies the manufacturer's effective values. A Manual core
    has no record, so the caller computes them from the entered dimensions and
    says so in `notes`. Keeping this separate from `CoreRecord` means no caller
    ever has to fabricate manufacturer provenance to get an estimate.

    `al_value_nh` is None exactly when the core has no manufacturer inductance
    factor, which is the Manual-core case. Both new fields are required: a
    default would let a caller silently omit the area and get an Unavailable
    A_L instead of a construction error.
    """

    path_length_m: float
    volume_m3: float
    effective_area_m2: float
    al_value_nh: float | None
    notes: tuple[str, ...] = field(default_factory=tuple)
```

- [ ] **Step 4: Fill both fields in the service**

In `src/inductor_designer/application/services/preliminary_inputs.py`, replace
the body of `core_magnetic_properties` after the `None` check with:

```python
    if isinstance(core, ManualCoreSelection):
        path_length_m = math.pi * (core.outer_diameter_m + core.inner_diameter_m) / 2.0
        effective_area_m2 = (
            (core.outer_diameter_m - core.inner_diameter_m) / 2.0
        ) * core.height_m
        return CoreMagneticProperties(
            path_length_m=path_length_m,
            volume_m3=effective_area_m2 * path_length_m,
            effective_area_m2=effective_area_m2,
            # A Manual core has no manufacturer inductance factor, so the A_L
            # check has no reference and reports itself unavailable.
            al_value_nh=None,
            notes=(MANUAL_CORE_PATH_NOTE,),
        )
    assert isinstance(core, CatalogCoreSelection)
    return CoreMagneticProperties(
        path_length_m=core.snapshot.path_length_m,
        volume_m3=core.snapshot.volume_m3,
        effective_area_m2=core.snapshot.effective_area_m2,
        al_value_nh=core.snapshot.al_value_nh,
        notes=(CATALOG_OVERRIDE_NOTE,) if core.overrides else (),
    )
```

- [ ] **Step 5: Update the two remaining construction sites**

In `tests/unit/simulation/conftest.py`, replace the `core=` argument:

```python
        core=CoreMagneticProperties(
            path_length_m=core_record.path_length_m,
            volume_m3=core_record.volume_m3,
            effective_area_m2=core_record.effective_area_m2,
            al_value_nh=core_record.al_value_nh,
        ),
```

In `tests/integration/test_preliminary_estimator.py`, replace the `core=`
argument with exactly the same four lines.

- [ ] **Step 6: Run the full suite**

```bash
$PY -m pytest -n 8 -q
```

Expected: PASS — 1161 passed (plus the 2 new tests), 7 skipped.

- [ ] **Step 7: Commit**

```bash
git add src/inductor_designer/simulation/preliminary_contracts.py src/inductor_designer/application/services/preliminary_inputs.py tests/unit/simulation/test_preliminary_contracts.py tests/unit/application/test_preliminary_inputs.py tests/unit/simulation/conftest.py tests/integration/test_preliminary_estimator.py
git commit -m "feat(simulation): carry core effective area and catalog A_L to the estimator"
```

---

### Task 2: The inductance estimator module

One pure module holding every new formula, plus its diagnostic codes.

**Files:**
- Create: `src/inductor_designer/simulation/inductance_estimate.py`
- Modify: `src/inductor_designer/simulation/preliminary_contracts.py:22-62`
  (new codes)
- Modify: `docs/superpowers/specs/2026-08-10-preliminary-inductance-and-al-check-design.md`
  (section 4: three codes the design did not enumerate)
- Test: `tests/unit/simulation/test_inductance_estimate.py`

**Interfaces:**
- Consumes: `CoreMagneticProperties` from Task 1; `FieldStrengths` and
  `FluxDensities` from `simulation.magnetic_estimate` (existing, unchanged).
- Produces:
  - `AlCheck(al_catalog_h: float, mu_r_initial: float, al_deviation: float)`
  - `CoreInductance(mu_r_effective: float, al_effective_h: float,
    catalog: AlCheck | None, notes: tuple[str, ...])`
  - `core_inductance(fields: FieldStrengths, densities: FluxDensities,
    core: CoreMagneticProperties) -> CoreInductance | PreliminaryValue`
  - `stored_energy_j(fields: FieldStrengths, densities: FluxDensities,
    core: CoreMagneticProperties) -> PreliminaryValue`
  - Note constants `INDUCTANCE_EXCLUSION_NOTE`, `AL_TOLERANCE_NOTE`,
    `ZERO_RIPPLE_NOTE`, `STORED_ENERGY_NOTE`.
- New codes on `DiagnosticCode`: `INDUCTANCE_NO_FLUX_DENSITY`,
  `INDUCTANCE_NO_EXCITATION`, `INDUCTANCE_NON_POSITIVE_AREA`,
  `INDUCTANCE_NOT_FINITE`, `AL_CHECK_NO_CATALOG_AL`,
  `STORED_ENERGY_NO_FLUX_DENSITY`, `STORED_ENERGY_NON_POSITIVE_VOLUME`,
  `CORE_GEOMETRY_NON_POSITIVE`, `CORE_GEOMETRY_NOT_FINITE`.

The `AlCheck` grouping is deliberate: the catalog `A_L`, the reference initial
permeability, and the deviation are either all present or all absent, so they
travel as one object instead of three independently-optional floats that every
consumer would have to re-check.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/simulation/test_inductance_estimate.py`:

```python
"""Inductance, A_L, and stored energy from an operating-point excursion.

Every case builds `FieldStrengths` and `FluxDensities` directly. That keeps
the permeability rules testable without a B-H series, a material record, or a
whole `PreliminaryRequest`.
"""

from __future__ import annotations

import pytest

from inductor_designer.simulation.inductance_estimate import (
    AL_TOLERANCE_NOTE,
    INDUCTANCE_EXCLUSION_NOTE,
    STORED_ENERGY_NOTE,
    ZERO_RIPPLE_NOTE,
    CoreInductance,
    core_inductance,
    stored_energy_j,
)
from inductor_designer.simulation.magnetic_estimate import (
    MU_0,
    FieldStrengths,
    FluxDensities,
)
from inductor_designer.simulation.preliminary_contracts import (
    CoreMagneticProperties,
    DiagnosticCode,
    PreliminaryValue,
    ResultState,
)

# 100 A/m of ripple on a 200 A/m bias: the excursion runs 100 to 300 A/m.
BIASED_FIELDS = FieldStrengths(
    h_ac_peak_a_per_m=100.0,
    h_dc_a_per_m=200.0,
    h_min_a_per_m=100.0,
    h_max_a_per_m=300.0,
)
# 0.2 T of swing over that 200 A/m span, so the incremental slope is 1e-3 H/m.
BIASED_DENSITIES = FluxDensities(
    b_dc_t=0.4,
    b_min_t=0.3,
    b_max_t=0.5,
    b_ac_peak_t=0.1,
    b_peak_magnitude_t=0.5,
    notes=(),
)
# A_e / l_e = 1e-3 m, so A_L effective is 1e-3 H/m * 1e-3 m = 1 uH per turn
# squared. The catalog value is deliberately higher, giving a -20 % roll-off.
CORE = CoreMagneticProperties(
    path_length_m=0.1,
    volume_m3=1e-5,
    effective_area_m2=1e-4,
    al_value_nh=1250.0,
)


def test_permeability_is_the_incremental_slope_over_the_excursion() -> None:
    result = core_inductance(BIASED_FIELDS, BIASED_DENSITIES, CORE)

    assert isinstance(result, CoreInductance)
    assert result.mu_r_effective == pytest.approx(1e-3 / MU_0)
    assert ZERO_RIPPLE_NOTE not in result.notes
    assert INDUCTANCE_EXCLUSION_NOTE in result.notes


def test_al_effective_is_permeability_times_area_over_path_length() -> None:
    result = core_inductance(BIASED_FIELDS, BIASED_DENSITIES, CORE)

    assert isinstance(result, CoreInductance)
    assert result.al_effective_h == pytest.approx(1e-6)


def test_the_catalog_check_reports_the_roll_off_against_the_manufacturer_value() -> None:
    result = core_inductance(BIASED_FIELDS, BIASED_DENSITIES, CORE)

    assert isinstance(result, CoreInductance)
    assert result.catalog is not None
    assert result.catalog.al_catalog_h == pytest.approx(1.25e-6)
    assert result.catalog.al_deviation == pytest.approx(-0.2)
    # The reference permeability is derived from the catalog A_L, never read
    # from the material record, so the two reported numbers cannot disagree.
    assert result.catalog.mu_r_initial == pytest.approx(
        1.25e-6 * CORE.path_length_m / (MU_0 * CORE.effective_area_m2)
    )
    assert AL_TOLERANCE_NOTE in result.notes


def test_an_effective_factor_above_catalog_reports_a_positive_deviation() -> None:
    """Sign check: the deviation must not be reported as a magnitude."""
    core = CoreMagneticProperties(
        path_length_m=0.1, volume_m3=1e-5, effective_area_m2=1e-4, al_value_nh=800.0
    )

    result = core_inductance(BIASED_FIELDS, BIASED_DENSITIES, core)

    assert isinstance(result, CoreInductance)
    assert result.catalog is not None
    assert result.catalog.al_deviation == pytest.approx(0.25)


def test_zero_ripple_falls_back_to_the_secant_at_the_bias_and_says_so() -> None:
    fields = FieldStrengths(
        h_ac_peak_a_per_m=0.0,
        h_dc_a_per_m=200.0,
        h_min_a_per_m=200.0,
        h_max_a_per_m=200.0,
    )
    densities = FluxDensities(
        b_dc_t=0.4,
        b_min_t=0.4,
        b_max_t=0.4,
        b_ac_peak_t=0.0,
        b_peak_magnitude_t=0.4,
        notes=(),
    )

    result = core_inductance(fields, densities, CORE)

    assert isinstance(result, CoreInductance)
    assert result.mu_r_effective == pytest.approx((0.4 / 200.0) / MU_0)
    assert ZERO_RIPPLE_NOTE in result.notes


def test_no_excitation_at_all_leaves_permeability_undefined() -> None:
    """No substituted initial permeability, no zero, no default."""
    fields = FieldStrengths(
        h_ac_peak_a_per_m=0.0,
        h_dc_a_per_m=0.0,
        h_min_a_per_m=0.0,
        h_max_a_per_m=0.0,
    )
    densities = FluxDensities(
        b_dc_t=0.0,
        b_min_t=0.0,
        b_max_t=0.0,
        b_ac_peak_t=0.0,
        b_peak_magnitude_t=0.0,
        notes=(),
    )

    result = core_inductance(fields, densities, CORE)

    assert isinstance(result, PreliminaryValue)
    assert result.state is ResultState.UNAVAILABLE
    assert result.code == DiagnosticCode.INDUCTANCE_NO_EXCITATION


def test_a_manual_core_has_no_reference_to_check_against() -> None:
    core = CoreMagneticProperties(
        path_length_m=0.1, volume_m3=1e-5, effective_area_m2=1e-4, al_value_nh=None
    )

    result = core_inductance(BIASED_FIELDS, BIASED_DENSITIES, core)

    assert isinstance(result, CoreInductance)
    assert result.catalog is None
    assert result.al_effective_h == pytest.approx(1e-6)
    assert AL_TOLERANCE_NOTE not in result.notes


@pytest.mark.parametrize("area", [0.0, -1e-4, float("inf"), float("nan")])
def test_an_unusable_area_refuses_al_instead_of_dividing(area: float) -> None:
    core = CoreMagneticProperties(
        path_length_m=0.1, volume_m3=1e-5, effective_area_m2=area, al_value_nh=1250.0
    )

    result = core_inductance(BIASED_FIELDS, BIASED_DENSITIES, core)

    assert isinstance(result, PreliminaryValue)
    assert result.code == DiagnosticCode.INDUCTANCE_NON_POSITIVE_AREA


def test_an_overflowing_slope_is_refused_not_reported() -> None:
    """A denormal field span with a finite flux swing overflows the slope.

    `PreliminaryValue` rejects a non-finite estimate, so without this guard
    the Preliminary screen would report "estimate failed" instead of a
    diagnosed row.
    """
    fields = FieldStrengths(
        h_ac_peak_a_per_m=5e-324,
        h_dc_a_per_m=0.0,
        h_min_a_per_m=0.0,
        h_max_a_per_m=5e-324,
    )

    result = core_inductance(fields, BIASED_DENSITIES, CORE)

    assert isinstance(result, PreliminaryValue)
    assert result.code == DiagnosticCode.INDUCTANCE_NOT_FINITE


def test_stored_energy_pairs_peak_flux_with_peak_field_over_the_volume() -> None:
    result = stored_energy_j(BIASED_FIELDS, BIASED_DENSITIES, CORE)

    assert result.state is ResultState.ESTIMATED
    # 0.5 * 0.5 T * 300 A/m * 1e-5 m^3
    assert result.value == pytest.approx(7.5e-4)
    assert STORED_ENERGY_NOTE in result.notes


def test_stored_energy_uses_the_larger_field_magnitude_of_the_excursion() -> None:
    """A bias smaller than the ripple drives the field negative; the peak is
    then |H_min|, and pairing it with |B| keeps both factors at one instant.
    """
    fields = FieldStrengths(
        h_ac_peak_a_per_m=300.0,
        h_dc_a_per_m=100.0,
        h_min_a_per_m=-200.0,
        h_max_a_per_m=400.0,
    )
    densities = FluxDensities(
        b_dc_t=0.2,
        b_min_t=-0.4,
        b_max_t=0.5,
        b_ac_peak_t=0.45,
        b_peak_magnitude_t=0.5,
        notes=(),
    )

    result = stored_energy_j(fields, densities, CORE)

    assert result.value == pytest.approx(0.5 * 0.5 * 400.0 * 1e-5)


def test_zero_excitation_still_stores_zero_energy() -> None:
    """Energy needs no permeability, so it survives what inductance refuses."""
    fields = FieldStrengths(
        h_ac_peak_a_per_m=0.0,
        h_dc_a_per_m=0.0,
        h_min_a_per_m=0.0,
        h_max_a_per_m=0.0,
    )
    densities = FluxDensities(
        b_dc_t=0.0,
        b_min_t=0.0,
        b_max_t=0.0,
        b_ac_peak_t=0.0,
        b_peak_magnitude_t=0.0,
        notes=(),
    )

    result = stored_energy_j(fields, densities, CORE)

    assert result.state is ResultState.ESTIMATED
    assert result.value == 0.0


@pytest.mark.parametrize("volume", [0.0, -1e-5, float("inf"), float("nan")])
def test_an_unusable_volume_refuses_stored_energy(volume: float) -> None:
    core = CoreMagneticProperties(
        path_length_m=0.1,
        volume_m3=volume,
        effective_area_m2=1e-4,
        al_value_nh=1250.0,
    )

    result = stored_energy_j(BIASED_FIELDS, BIASED_DENSITIES, core)

    assert result.state is ResultState.UNAVAILABLE
    assert result.code == DiagnosticCode.STORED_ENERGY_NON_POSITIVE_VOLUME
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
$PY -m pytest tests/unit/simulation/test_inductance_estimate.py -q
```

Expected: FAIL — `ModuleNotFoundError: No module named
'inductor_designer.simulation.inductance_estimate'`.

- [ ] **Step 3: Add the diagnostic codes**

In `src/inductor_designer/simulation/preliminary_contracts.py`, insert after the
`CURRENT_DENSITY_NO_CONDUCTOR` line:

```python
    INDUCTANCE_NO_FLUX_DENSITY = "inductance.no_flux_density"
    INDUCTANCE_NO_EXCITATION = "inductance.no_excitation"
    INDUCTANCE_NON_POSITIVE_AREA = "inductance.non_positive_area"
    INDUCTANCE_NOT_FINITE = "inductance.not_finite"

    AL_CHECK_NO_CATALOG_AL = "al_check.no_catalog_al"

    STORED_ENERGY_NO_FLUX_DENSITY = "stored_energy.no_flux_density"
    STORED_ENERGY_NON_POSITIVE_VOLUME = "stored_energy.non_positive_volume"

    # The effective-geometry echo is reported independently of flux density,
    # so it needs its own reasons rather than borrowing the flux-density or
    # core-loss ones.
    CORE_GEOMETRY_NON_POSITIVE = "core_geometry.non_positive"
    CORE_GEOMETRY_NOT_FINITE = "core_geometry.not_finite"
```

- [ ] **Step 4: Write the module**

Create `src/inductor_designer/simulation/inductance_estimate.py`:

```python
"""Inductance, inductance factor, and stored energy at one operating point.

Every value here is a lumped effective-core estimate derived from the field
strengths and flux densities the magnetic estimate already produced. None of
them is a solver result, and none models fringing, leakage, or winding
capacitance.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from inductor_designer.simulation.magnetic_estimate import (
    MU_0,
    FieldStrengths,
    FluxDensities,
)
from inductor_designer.simulation.preliminary_contracts import (
    CoreMagneticProperties,
    DiagnosticCode,
    PreliminaryValue,
    estimated,
    unavailable,
)

INDUCTANCE_EXCLUSION_NOTE = (
    "incremental-permeability inductance estimate at the DC bias; excludes "
    "air-gap fringing, leakage inductance, and winding self-capacitance"
)
AL_TOLERANCE_NOTE = (
    "the catalog inductance factor is a low-signal value, so the reported "
    "deviation mixes DC-bias roll-off with catalog tolerance and cannot "
    "separate them"
)
ZERO_RIPPLE_NOTE = (
    "zero AC ripple: permeability evaluated as the secant B_dc / H_dc at the "
    "DC bias instead of the incremental slope"
)
STORED_ENERGY_NOTE = (
    "stored energy is the effective-core-volume estimate "
    "0.5 * B_peak * H_peak * V_e; energy stored in the winding window and in "
    "leakage paths is excluded"
)


@dataclass(frozen=True, slots=True)
class AlCheck:
    """The catalog reference and the deviation from it.

    These three travel together because they are either all available or all
    absent: without a manufacturer `A_L` there is no reference, no derived
    initial permeability, and no deviation.
    """

    al_catalog_h: float
    mu_r_initial: float
    al_deviation: float


@dataclass(frozen=True, slots=True)
class CoreInductance:
    mu_r_effective: float
    al_effective_h: float
    catalog: AlCheck | None
    notes: tuple[str, ...]


def _absolute_permeability(
    fields: FieldStrengths, densities: FluxDensities
) -> tuple[float, tuple[str, ...]] | PreliminaryValue:
    """dB/dH over the operating excursion, or the secant when there is no ripple.

    The incremental slope is what a converter sees at the bias point. With no
    AC ripple the excursion collapses to a point and the slope is 0/0, so the
    secant through the bias is used and labelled. With no excitation at all
    there is nothing to differentiate and nothing to draw a secant through.
    """
    span_a_per_m = fields.h_max_a_per_m - fields.h_min_a_per_m
    if span_a_per_m > 0.0:
        permeability = (densities.b_max_t - densities.b_min_t) / span_a_per_m
        notes: tuple[str, ...] = ()
    elif fields.h_dc_a_per_m != 0.0:
        permeability = densities.b_dc_t / fields.h_dc_a_per_m
        notes = (ZERO_RIPPLE_NOTE,)
    else:
        return unavailable(
            DiagnosticCode.INDUCTANCE_NO_EXCITATION,
            "The operating point carries neither AC nor DC ampere-turns, so "
            "permeability is undefined and inductance cannot be estimated. "
            "The material's initial permeability is not substituted.",
        )
    if not math.isfinite(permeability):
        return unavailable(
            DiagnosticCode.INDUCTANCE_NOT_FINITE,
            "The field excursion is too small for the flux swing, so the "
            "permeability slope overflows; inductance is not reported.",
        )
    return permeability, notes


def core_inductance(
    fields: FieldStrengths,
    densities: FluxDensities,
    core: CoreMagneticProperties,
) -> CoreInductance | PreliminaryValue:
    """The core-level inductance factor, or the diagnostic explaining its absence.

    `A_L` is a core property: every winding's inductance is `turns**2 * A_L`,
    which the caller applies. The path length needs no guard here -- flux
    densities exist only after `field_strengths` has already refused a
    non-positive or non-finite path length.
    """
    if not (core.effective_area_m2 > 0.0 and math.isfinite(core.effective_area_m2)):
        return unavailable(
            DiagnosticCode.INDUCTANCE_NON_POSITIVE_AREA,
            "Core effective area must be a positive finite number; "
            f"got {core.effective_area_m2:g} m^2. The core dimensions are out "
            "of range, so the inductance factor cannot be estimated.",
        )
    permeability = _absolute_permeability(fields, densities)
    if isinstance(permeability, PreliminaryValue):
        return permeability
    mu_abs, notes = permeability

    geometry_factor = core.effective_area_m2 / core.path_length_m
    al_effective_h = mu_abs * geometry_factor
    notes = (INDUCTANCE_EXCLUSION_NOTE, *notes)

    if core.al_value_nh is None:
        return CoreInductance(
            mu_r_effective=mu_abs / MU_0,
            al_effective_h=al_effective_h,
            catalog=None,
            notes=notes,
        )

    # `CoreRecord` validates `al_value_nh > 0`, and a Manual core reports None
    # above, so no reachable path divides by zero here.
    al_catalog_h = core.al_value_nh * 1e-9
    return CoreInductance(
        mu_r_effective=mu_abs / MU_0,
        al_effective_h=al_effective_h,
        catalog=AlCheck(
            al_catalog_h=al_catalog_h,
            mu_r_initial=al_catalog_h / (MU_0 * geometry_factor),
            al_deviation=al_effective_h / al_catalog_h - 1.0,
        ),
        notes=(*notes, AL_TOLERANCE_NOTE),
    )


def stored_energy_j(
    fields: FieldStrengths,
    densities: FluxDensities,
    core: CoreMagneticProperties,
) -> PreliminaryValue:
    """Peak energy stored in the effective core volume.

    Needs no permeability, so it stays available where inductance is refused
    for want of excitation: at zero excitation the stored energy really is
    zero. `B` and `H` are both taken at their peak magnitude so the two
    factors describe the same instant of the cycle.
    """
    if not (core.volume_m3 > 0.0 and math.isfinite(core.volume_m3)):
        return unavailable(
            DiagnosticCode.STORED_ENERGY_NON_POSITIVE_VOLUME,
            "Core effective volume must be a positive finite number; "
            f"got {core.volume_m3:g} m^3. Stored energy is not reported.",
        )
    h_peak_a_per_m = max(abs(fields.h_min_a_per_m), abs(fields.h_max_a_per_m))
    return estimated(
        0.5 * densities.b_peak_magnitude_t * h_peak_a_per_m * core.volume_m3,
        (STORED_ENERGY_NOTE,),
    )
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
$PY -m pytest tests/unit/simulation/test_inductance_estimate.py tests/unit/simulation/test_preliminary_contracts.py -q
```

Expected: PASS. `test_preliminary_contracts.py` includes a code-uniqueness
check that now covers the nine new codes.

- [ ] **Step 6: Amend the design's diagnostic table**

Three codes were not enumerated in the design. In
`docs/superpowers/specs/2026-08-10-preliminary-inductance-and-al-check-design.md`,
add these rows to the section 4 table:

```markdown
| `inductance.not_finite` | The field excursion is too small for the flux swing, so the permeability slope overflows. Prevents a non-finite estimate from becoming a screen-level failure. |
| `core_geometry.non_positive` | An echoed effective dimension is not positive. |
| `core_geometry.not_finite` | An echoed effective dimension is not a finite number. |
```

and append this paragraph to section 5.3:

> The effective-geometry echo is evaluated from `CoreMagneticProperties`
> independently of flux density, in the same way wire length is evaluated
> independently of wire loss. A missing B-H series at the requested
> temperature must not make the core's effective area read Unavailable, which
> is why the echo carries its own `core_geometry.*` reasons.

- [ ] **Step 7: Commit**

```bash
git add src/inductor_designer/simulation/inductance_estimate.py src/inductor_designer/simulation/preliminary_contracts.py tests/unit/simulation/test_inductance_estimate.py docs/superpowers/specs/2026-08-10-preliminary-inductance-and-al-check-design.md
git commit -m "feat(simulation): estimate inductance factor, permeability, and stored energy"
```

---

### Task 3: Report the new quantities from the estimator

**Files:**
- Modify: `src/inductor_designer/simulation/preliminary.py`
- Test: `tests/unit/simulation/test_preliminary.py`

**Interfaces:**
- Consumes: `core_inductance`, `stored_energy_j`, `CoreInductance` (Task 2);
  extended `CoreMagneticProperties` (Task 1).
- Produces:
  - `CorePreliminary` gains, after `core_loss`: `effective_area`,
    `path_length`, `volume`, `mu_r_effective`, `mu_r_initial`, `al_catalog`,
    `al_effective`, `al_deviation`, `stored_energy` — all `PreliminaryValue`,
    all required.
  - `WindingPreliminary` gains `inductance: PreliminaryValue`, after
    `wire_loss`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/simulation/test_preliminary.py`:

```python
def test_the_core_reports_its_inductance_factor_and_stored_energy(
    sample_request: PreliminaryRequest,
) -> None:
    result = estimate_preliminary(sample_request)

    assert result.core.al_effective.state is ResultState.ESTIMATED
    assert result.core.mu_r_effective.state is ResultState.ESTIMATED
    assert result.core.stored_energy.state is ResultState.ESTIMATED
    assert result.core.al_deviation.state is ResultState.ESTIMATED
    assert INDUCTANCE_EXCLUSION_NOTE in result.notes
    assert STORED_ENERGY_NOTE in result.notes


def test_every_winding_inductance_is_its_turns_squared_times_the_core_factor(
    sample_request: PreliminaryRequest,
) -> None:
    result = estimate_preliminary(sample_request)

    al_effective = result.core.al_effective.value
    assert al_effective is not None
    for row, definition in zip(
        result.windings, sample_request.project.design.windings, strict=True
    ):
        assert row.inductance.value == pytest.approx(definition.turns**2 * al_effective)


def test_the_effective_geometry_echo_reports_the_values_actually_used(
    sample_request: PreliminaryRequest,
) -> None:
    result = estimate_preliminary(sample_request)

    core = sample_request.core
    assert core is not None
    assert result.core.effective_area.value == core.effective_area_m2
    assert result.core.path_length.value == core.path_length_m
    assert result.core.volume.value == core.volume_m3


def test_a_missing_bh_series_does_not_hide_the_core_geometry(
    sample_request: PreliminaryRequest,
) -> None:
    """The echo is independent of flux density: the dimensions are still known."""
    project = replace(
        sample_request.project,
        operating_point=replace(
            sample_request.project.operating_point, core_temperature_c=85.0
        ),
    )

    result = estimate_preliminary(replace(sample_request, project=project))

    assert result.core.b_dc.state is ResultState.UNAVAILABLE
    assert result.core.effective_area.state is ResultState.ESTIMATED
    assert result.core.al_effective.state is ResultState.UNAVAILABLE
    assert result.core.al_effective.code == DiagnosticCode.INDUCTANCE_NO_FLUX_DENSITY
    assert result.core.stored_energy.code == DiagnosticCode.STORED_ENERGY_NO_FLUX_DENSITY


def test_no_core_leaves_the_geometry_echo_unavailable(
    sample_request: PreliminaryRequest,
) -> None:
    result = estimate_preliminary(replace(sample_request, core=None))

    assert (
        result.core.effective_area.code
        == DiagnosticCode.FLUX_DENSITY_NO_CORE_SELECTED
    )
    assert result.core.al_effective.code == DiagnosticCode.INDUCTANCE_NO_FLUX_DENSITY
    assert result.windings[0].inductance.code == (
        DiagnosticCode.INDUCTANCE_NO_FLUX_DENSITY
    )


def test_a_core_without_a_catalog_al_still_reports_inductance(
    sample_request: PreliminaryRequest,
) -> None:
    core = sample_request.core
    assert core is not None
    request = replace(sample_request, core=replace(core, al_value_nh=None))

    result = estimate_preliminary(request)

    assert result.core.al_effective.state is ResultState.ESTIMATED
    assert result.core.al_catalog.code == DiagnosticCode.AL_CHECK_NO_CATALOG_AL
    assert result.core.al_deviation.code == DiagnosticCode.AL_CHECK_NO_CATALOG_AL
    assert result.core.mu_r_initial.code == DiagnosticCode.AL_CHECK_NO_CATALOG_AL
    assert result.windings[0].inductance.state is ResultState.ESTIMATED


def test_inductance_survives_a_missing_conductor_record(
    sample_request: PreliminaryRequest,
) -> None:
    """Inductance depends on the core, not on the copper, unlike every other
    winding quantity. Dropping the conductor must not take it down with the
    current densities.
    """
    result = estimate_preliminary(replace(sample_request, conductors_by_winding={}))

    assert result.windings[0].j_ac_rms.state is ResultState.UNAVAILABLE
    assert result.windings[0].inductance.state is ResultState.ESTIMATED


def test_a_non_finite_volume_refuses_only_stored_energy_and_core_loss(
    sample_request: PreliminaryRequest,
) -> None:
    core = sample_request.core
    assert core is not None
    request = replace(sample_request, core=replace(core, volume_m3=float("inf")))

    result = estimate_preliminary(request)

    assert result.core.volume.code == DiagnosticCode.CORE_GEOMETRY_NOT_FINITE
    assert (
        result.core.stored_energy.code
        == DiagnosticCode.STORED_ENERGY_NON_POSITIVE_VOLUME
    )
    assert result.core.al_effective.state is ResultState.ESTIMATED
```

Add to that file's imports whatever it does not already have:

```python
import pytest

from inductor_designer.simulation.inductance_estimate import (
    INDUCTANCE_EXCLUSION_NOTE,
    STORED_ENERGY_NOTE,
)
```

`replace`, `estimate_preliminary`, `PreliminaryRequest`, `ResultState`, and
`DiagnosticCode` are already imported there; confirm before adding duplicates.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
$PY -m pytest tests/unit/simulation/test_preliminary.py -q
```

Expected: FAIL — `AttributeError: 'CorePreliminary' object has no attribute
'al_effective'`.

- [ ] **Step 3: Extend the result dataclasses**

In `src/inductor_designer/simulation/preliminary.py`, add to the imports:

```python
from inductor_designer.simulation.inductance_estimate import (
    CoreInductance,
    core_inductance,
    stored_energy_j,
)
```

Append to `WindingPreliminary`:

```python
    # Depends on the core, not on this winding's conductor record, so it stays
    # estimated when the copper quantities are refused.
    inductance: PreliminaryValue
```

Append to `CorePreliminary`:

```python
    effective_area: PreliminaryValue
    path_length: PreliminaryValue
    volume: PreliminaryValue
    mu_r_effective: PreliminaryValue
    mu_r_initial: PreliminaryValue
    al_catalog: PreliminaryValue
    al_effective: PreliminaryValue
    al_deviation: PreliminaryValue
    stored_energy: PreliminaryValue
```

- [ ] **Step 4: Build the geometry echo and widen `_core_all`**

Insert above `_core_all`:

```python
@dataclass(frozen=True, slots=True)
class _GeometryEcho:
    """The effective dimensions actually used, reported independently of flux.

    A missing B-H series must not make the core's area read Unavailable, so
    this is evaluated from `CoreMagneticProperties` alone -- the same reason
    wire length is evaluated independently of wire loss.
    """

    effective_area: PreliminaryValue
    path_length: PreliminaryValue
    volume: PreliminaryValue


def _echoed(value: float, name: str, notes: tuple[str, ...]) -> PreliminaryValue:
    if not math.isfinite(value):
        return unavailable(
            DiagnosticCode.CORE_GEOMETRY_NOT_FINITE,
            f"Core {name} is not a finite number, so the core dimensions are "
            "out of range.",
        )
    if not value > 0.0:
        return unavailable(
            DiagnosticCode.CORE_GEOMETRY_NON_POSITIVE,
            f"Core {name} must be positive; got {value:g}.",
        )
    return estimated(value, notes)


def _geometry_echo(core: CoreMagneticProperties) -> _GeometryEcho:
    return _GeometryEcho(
        effective_area=_echoed(core.effective_area_m2, "effective area", core.notes),
        path_length=_echoed(core.path_length_m, "magnetic path length", core.notes),
        volume=_echoed(core.volume_m3, "effective volume", core.notes),
    )


def _no_geometry(reason: PreliminaryValue) -> _GeometryEcho:
    """With no core there are no dimensions to echo, and the reason is exactly
    the one flux density reports: no core is selected.
    """
    return _GeometryEcho(effective_area=reason, path_length=reason, volume=reason)
```

Two functions rather than one taking `core: ... | None`: the success branch
has no reason value to pass, and inventing a placeholder `PreliminaryValue`
would raise, because `unavailable("", "")` requires a real code and message.

Add `import math` to the module's imports if it is not already there.

Replace `_core_all` with:

```python
def _core_all(
    flux_reason: PreliminaryValue, geometry: _GeometryEcho
) -> CorePreliminary:
    """One flux-density reason, reported identically for every B quantity.

    Core loss, inductance, and stored energy each get their OWN diagnostic:
    stamping the flux-density code onto them would claim they failed for a
    reason they didn't -- they failed because flux density was unavailable.
    The geometry echo does not depend on flux density and is passed in.
    """
    core_loss_reason = unavailable(
        DiagnosticCode.CORE_LOSS_NO_FLUX_DENSITY,
        "Core loss requires a flux-density estimate, which is unavailable: "
        f"{flux_reason.message}",
    )
    inductance_reason = unavailable(
        DiagnosticCode.INDUCTANCE_NO_FLUX_DENSITY,
        "Inductance requires a flux-density estimate, which is unavailable: "
        f"{flux_reason.message}",
    )
    energy_reason = unavailable(
        DiagnosticCode.STORED_ENERGY_NO_FLUX_DENSITY,
        "Stored energy requires a flux-density estimate, which is "
        f"unavailable: {flux_reason.message}",
    )
    return CorePreliminary(
        b_dc=flux_reason,
        b_min=flux_reason,
        b_max=flux_reason,
        b_ac_peak=flux_reason,
        b_peak_magnitude=flux_reason,
        core_loss=core_loss_reason,
        effective_area=geometry.effective_area,
        path_length=geometry.path_length,
        volume=geometry.volume,
        mu_r_effective=inductance_reason,
        mu_r_initial=inductance_reason,
        al_catalog=inductance_reason,
        al_effective=inductance_reason,
        al_deviation=inductance_reason,
        stored_energy=energy_reason,
    )
```

- [ ] **Step 5: Compute the estimates in `_core_estimates`**

Replace `_core_estimates` with:

```python
def _core_estimates(
    request: PreliminaryRequest,
    fields: FieldStrengths,
    densities: FluxDensities,
    core: CoreMagneticProperties,
    geometry: _GeometryEcho,
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
        core_volume_m3=core.volume_m3,
    )
    # The core's own notes describe how its path length and volume were
    # obtained, which is an assumption behind every B value below.
    notes = densities.notes + core.notes
    inductance = core_inductance(fields, densities, core)
    if isinstance(inductance, CoreInductance):
        inductance_notes = inductance.notes + core.notes
        mu_r_effective = estimated(inductance.mu_r_effective, inductance_notes)
        al_effective = estimated(inductance.al_effective_h, inductance_notes)
        if inductance.catalog is None:
            no_reference = unavailable(
                DiagnosticCode.AL_CHECK_NO_CATALOG_AL,
                "The selected core has no manufacturer inductance factor, so "
                "the effective A_L has no reference to be checked against.",
            )
            al_catalog = no_reference
            al_deviation = no_reference
            mu_r_initial = no_reference
        else:
            al_catalog = estimated(inductance.catalog.al_catalog_h, inductance_notes)
            al_deviation = estimated(inductance.catalog.al_deviation, inductance_notes)
            mu_r_initial = estimated(inductance.catalog.mu_r_initial, inductance_notes)
    else:
        mu_r_effective = inductance
        al_effective = inductance
        al_catalog = inductance
        al_deviation = inductance
        mu_r_initial = inductance
    return CorePreliminary(
        b_dc=estimated(densities.b_dc_t, notes),
        b_min=estimated(densities.b_min_t, notes),
        b_max=estimated(densities.b_max_t, notes),
        b_ac_peak=estimated(densities.b_ac_peak_t, notes),
        b_peak_magnitude=estimated(densities.b_peak_magnitude_t, notes),
        core_loss=loss,
        effective_area=geometry.effective_area,
        path_length=geometry.path_length,
        volume=geometry.volume,
        mu_r_effective=mu_r_effective,
        mu_r_initial=mu_r_initial,
        al_catalog=al_catalog,
        al_effective=al_effective,
        al_deviation=al_deviation,
        stored_energy=stored_energy_j(fields, densities, core),
    )
```

- [ ] **Step 6: Give each winding its inductance**

Insert above `_winding_row`:

```python
def _winding_inductance(turns: int, al_effective: PreliminaryValue) -> PreliminaryValue:
    """`turns**2 * A_L`, or the core's own reason unchanged.

    Returning `al_effective` itself is deliberate: the winding's inductance
    failed for exactly the core's reason, so it carries the same code, message
    and notes rather than a paraphrase.
    """
    if al_effective.state is not ResultState.ESTIMATED or al_effective.value is None:
        return al_effective
    return estimated(turns**2 * al_effective.value, al_effective.notes)
```

Change `_winding_row`'s signature to

```python
def _winding_row(
    request: PreliminaryRequest, winding_id: str, inductance: PreliminaryValue
) -> WindingPreliminary:
```

and add `inductance=inductance,` to **both** `WindingPreliminary(...)` returns
inside it (the no-conductor early return and the final one).

In `estimate_preliminary`, replace the `windings = tuple(...)` expression with:

```python
    windings = tuple(
        _winding_row(
            request,
            definition.winding_id,
            _winding_inductance(definition.turns, core.al_effective),
        )
        for definition in design.windings
    )
```

- [ ] **Step 7: Pass the geometry echo through `estimate_preliminary`**

Replace the core branches of `estimate_preliminary` with the following. Only
the `_core_all` / `_core_estimates` call sites change: every diagnostic
message, and both explanatory comments, stay exactly as they are today.

```python
    if request.core is None:
        reason = unavailable(
            DiagnosticCode.FLUX_DENSITY_NO_CORE_SELECTED,
            "No core is selected, so core flux density and core loss cannot "
            "be estimated.",
        )
        core = _core_all(reason, _no_geometry(reason))
    elif material is None:
        core = _core_all(
            unavailable(
                DiagnosticCode.FLUX_DENSITY_NO_MATERIAL_SELECTED,
                "No core material revision is selected, so core flux density "
                "and core loss cannot be estimated.",
            ),
            _geometry_echo(request.core),
        )
    elif (
        isinstance(design.core, ManualCoreSelection)
        and not design.manual_material_compatibility_acknowledged
    ):
        # Specification section 4.1: a Manual core paired with a material
        # requires a visible compatibility acknowledgment before Preliminary
        # can treat the pair as complete. Generation and solve already refuse
        # an unacknowledged pair (`run_planning.py`, `domain/validation.py`);
        # this closes the same gap here. Winding quantities do not depend on
        # the core, so they stay estimated below.
        core = _core_all(
            unavailable(
                DiagnosticCode.FLUX_DENSITY_MANUAL_COMPATIBILITY_UNACKNOWLEDGED,
                "The Manual core and pinned material pair is not yet "
                "acknowledged, so core flux density and core loss cannot be "
                "estimated. Confirm material compatibility on the Core & "
                "Material screen.",
            ),
            _geometry_echo(request.core),
        )
    else:
        # Built from the design itself, never taken from the caller, so this
        # can never disagree with WindingDefinition.turns.
        turns_by_winding = {
            definition.winding_id: definition.turns for definition in design.windings
        }
        fields = field_strengths(
            request.project.operating_point,
            turns_by_winding,
            request.core.path_length_m,
        )
        geometry = _geometry_echo(request.core)
        if isinstance(fields, PreliminaryValue):
            core = _core_all(fields, geometry)
        else:
            densities = flux_densities(
                material,
                fields,
                request.project.operating_point.core_temperature_c,
            )
            if isinstance(densities, PreliminaryValue):
                core = _core_all(densities, geometry)
            else:
                core = _core_estimates(
                    request, fields, densities, request.core, geometry
                )
```

Note the asymmetry, which is the point of the whole step: the no-core branch
uses `_no_geometry(reason)` because there are no dimensions to report, while
every other branch uses `_geometry_echo(request.core)` — a core is selected, so
its dimensions are known and must stay visible even when flux density is
refused.

- [ ] **Step 8: Carry the new notes into the assumptions list**

In `estimate_preliminary`, replace the notes-aggregation loop's tuple with:

```python
    for value in (
        core.b_dc,
        core.core_loss,
        core.al_effective,
        core.stored_energy,
        *(row.wire_loss for row in windings),
    ):
```

- [ ] **Step 9: Run the tests to verify they pass**

```bash
$PY -m pytest tests/unit/simulation tests/integration/test_preliminary_estimator.py -q
```

Expected: PASS. Any `TypeError: CorePreliminary.__init__() missing ...`
failure in another test module means a fixture there also builds
`CorePreliminary` — fix it in Task 4, which owns that fixture.

- [ ] **Step 10: Commit**

```bash
git add src/inductor_designer/simulation/preliminary.py tests/unit/simulation/test_preliminary.py
git commit -m "feat(simulation): report inductance, A_L check, and stored energy per estimate"
```

---

### Task 4: Engineering units and rows

**Files:**
- Modify: `src/inductor_designer/ui/preliminary_rows.py`
- Test: `tests/unit/ui/test_preliminary_rows.py`

**Interfaces:**
- Consumes: the extended `CorePreliminary` / `WindingPreliminary` (Task 3).
- Produces: `core_rows` returns 15 rows, the first 6 unchanged and in the same
  order (existing tests index `coreRows[5]` for core loss). `winding_rows`
  dicts gain the key `inductance`.

- [ ] **Step 1: Write the failing tests**

In `tests/unit/ui/test_preliminary_rows.py`, extend `make_result()`'s
`CorePreliminary(...)` with:

```python
            effective_area=estimated(6.56e-5),
            path_length=estimated(0.0814),
            volume=estimated(5.34e-6),
            mu_r_effective=estimated(795.7747154594767),
            mu_r_initial=estimated(994.7183943243459),
            al_catalog=estimated(1.25e-6),
            al_effective=estimated(1e-6),
            al_deviation=estimated(-0.2),
            stored_energy=estimated(7.5e-4),
```

and its `WindingPreliminary(...)` with:

```python
                inductance=estimated(1e-4),
```

Replace `test_core_rows_cover_the_specified_core_summary` with:

```python
def test_core_rows_cover_the_specified_core_summary() -> None:
    rows = core_rows(make_result())

    assert [row["label"] for row in rows] == [
        "DC flux density",
        "AC flux-density swing",
        "Minimum flux density",
        "Maximum flux density",
        "Peak flux-density magnitude",
        "Core loss",
        "Effective area A_e",
        "Magnetic path length l_e",
        "Effective volume V_e",
        "Effective relative permeability",
        "Initial relative permeability (from catalog A_L)",
        "Catalog A_L",
        "Effective A_L",
        "A_L deviation",
        "Stored energy",
    ]
    assert rows[0]["text"] == "84.700 mT"
    assert rows[5]["state"] == ResultState.UNAVAILABLE.value
    assert rows[6]["text"] == "65.6000 mm²"
    assert rows[7]["text"] == "81.40 mm"
    assert rows[8]["text"] == "5.340 cm³"
    assert rows[9]["text"] == "795.8"
    assert rows[10]["text"] == "994.7"
    assert rows[11]["text"] == "1250.00 nH/N²"
    assert rows[12]["text"] == "1000.00 nH/N²"
    assert rows[13]["text"] == "-20.00 %"
    assert rows[14]["text"] == "0.7500 mJ"


def test_a_dimensionless_cell_carries_no_unit_suffix_or_trailing_space() -> None:
    """A permeability has no unit, and " 795.8 " would show as a stray space."""
    assert cell(estimated(795.7747154594767), DIMENSIONLESS)["text"] == "795.8"
```

Add `"inductance"` coverage to the winding test:

```python
    assert row["inductance"]["text"] == "100.000 µH"
```

Extend the imports in that file with `DIMENSIONLESS`.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
$PY -m pytest tests/unit/ui/test_preliminary_rows.py -q
```

Expected: FAIL — `ImportError: cannot import name 'DIMENSIONLESS'`.

- [ ] **Step 3: Add the units and rows**

In `src/inductor_designer/ui/preliminary_rows.py`, add after `WATT`:

```python
MICROHENRY = DisplayUnit("µH", 1e6, 3)
NANOHENRY_PER_TURNS_SQUARED = DisplayUnit("nH/N²", 1e9, 2)
CUBIC_CENTIMETRE = DisplayUnit("cm³", 1e6, 3)
MILLIJOULE = DisplayUnit("mJ", 1000.0, 4)
PERCENT = DisplayUnit("%", 100.0, 2)
# A permeability ratio has no unit. `cell` strips the trailing separator so
# the value does not render with a stray space after it.
DIMENSIONLESS = DisplayUnit("", 1.0, 1)
```

In `cell`, change the estimated-value branch to:

```python
    if value.state is ResultState.ESTIMATED and value.value is not None:
        text = f"{value.value * unit.scale:.{unit.decimals}f} {unit.suffix}".rstrip()
```

Append to `core_rows`' returned list, after the `"Core loss"` entry:

```python
        _labelled("Effective area A_e", core.effective_area, SQUARE_MILLIMETRE),
        _labelled("Magnetic path length l_e", core.path_length, MILLIMETRE),
        _labelled("Effective volume V_e", core.volume, CUBIC_CENTIMETRE),
        _labelled(
            "Effective relative permeability", core.mu_r_effective, DIMENSIONLESS
        ),
        _labelled(
            "Initial relative permeability (from catalog A_L)",
            core.mu_r_initial,
            DIMENSIONLESS,
        ),
        _labelled("Catalog A_L", core.al_catalog, NANOHENRY_PER_TURNS_SQUARED),
        _labelled("Effective A_L", core.al_effective, NANOHENRY_PER_TURNS_SQUARED),
        _labelled("A_L deviation", core.al_deviation, PERCENT),
        _labelled("Stored energy", core.stored_energy, MILLIJOULE),
```

Add to each dict `winding_rows` builds:

```python
            "inductance": cell(row.inductance, MICROHENRY),
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
$PY -m pytest tests/unit/ui/test_preliminary_rows.py -q
```

Expected: PASS. If a rounding assertion is off by one digit, trust the
computed value and fix the expected string — the units, not the physics, are
under test here.

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/ui/preliminary_rows.py tests/unit/ui/test_preliminary_rows.py
git commit -m "feat(ui): add inductance, A_L, permeability, and energy rows"
```

---

### Task 5: The Preliminary screen

**Files:**
- Modify: `src/inductor_designer/ui/qml/PreliminaryPage.qml:124-136`
  (header) and `:152-198` (row delegate)
- Test: `tests/ui/test_flow_screens_qml.py:141,176,184-185,204`
- Test: `tests/ui/test_preliminary_controller.py:38`

The `Inductance` column is appended last so the existing eight columns keep
their positions, and the core rows are appended after `Core loss` so
`coreRows[5]` still identifies core loss in the tests that index it.

**Interfaces:**
- Consumes: `windingRows[i]["inductance"]` and the 15-row `coreRows`
  (Task 4). The controller needs no change — it already forwards whatever
  `core_rows` and `winding_rows` return.

- [ ] **Step 1: Update the failing expectations**

In `tests/ui/test_flow_screens_qml.py`:

- line 141: `assert len(header_cells) == len(row_cells) == 9`
- line 176: `for column in range(9):`
- lines 184-185: `range(9)` in both comprehensions
- line 204: `assert root.findChild(QObject, "preliminaryCoreTable").property("count") == 15`

In `tests/ui/test_preliminary_controller.py` line 38:
`assert len(controller.coreRows) == 15`

Add to `tests/ui/test_preliminary_controller.py`:

```python
def test_every_winding_row_reports_an_inductance_and_the_permeability_used() -> None:
    """`make_project_with_material()` pins a record with no B-H series, so flux
    density comes from its `relative_permeability = 60.0`. The incremental
    slope of a linear model is that same permeability, which makes the
    reported effective permeability exactly 60 -- a fixed number to assert
    against rather than a re-derivation of the formula under test.
    """
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project_with_material())
    controller = PreliminaryController(session, CATALOG)

    assert controller.windingRows[0]["inductance"]["state"] == (
        ResultState.ESTIMATED.value
    )
    assert controller.coreRows[9]["label"] == "Effective relative permeability"
    assert controller.coreRows[9]["text"] == "60.0"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
$PY -m pytest tests/ui/test_flow_screens_qml.py tests/ui/test_preliminary_controller.py -q
```

Expected: FAIL — `assert 8 == 9` on the header/row cell count, and
`assert 6 == 15` on the core table count.

- [ ] **Step 3: Add the column**

In `src/inductor_designer/ui/qml/PreliminaryPage.qml`, add as the last child
of the `preliminaryWindingTableHeader` `RowLayout`:

```qml
                Label { Layout.preferredWidth: 110; text: qsTr("Inductance"); elide: Text.ElideRight; color: "#6d7a7e" }
```

and as the last child of the row delegate's inner `RowLayout` (after the wire
loss `Label`):

```qml
                        Label {
                            Layout.preferredWidth: 110
                            text: modelData.inductance.text
                            elide: Text.ElideRight
                            color: preliminaryPage.stateColor(modelData.inductance.state)
                        }
```

No `Layout.fillWidth` on either, matching the fixed-width column rule the
surrounding comment documents.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
$PY -m pytest tests/ui -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/ui/qml/PreliminaryPage.qml tests/ui/test_flow_screens_qml.py tests/ui/test_preliminary_controller.py
git commit -m "feat(ui): show inductance and the A_L check on the Preliminary screen"
```

---

### Task 6: Carry inductance into Review

**Files:**
- Modify: `src/inductor_designer/ui/review_controller.py:173-180`
- Test: `tests/ui/test_review_controller.py`

Review already maps `coreRows` generically, so the nine new core rows appear
without any change. Only the per-winding line needs adding.

- [ ] **Step 1: Write the failing test**

Add to `tests/ui/test_review_controller.py`:

```python
def test_review_reports_each_winding_inductance() -> None:
    _, _, controller = build()

    rows = [
        row
        for section in controller.sections
        if section["title"] == "Preliminary estimates"
        for row in section["rows"]
    ]

    assert any(row["label"] == "w1 inductance" for row in rows)
    assert any(row["label"] == "Effective A_L" for row in rows)
```

Use the file's existing controller-construction helper (see
`test_review_shows_the_paired_core_material_operating_point_and_estimates`)
rather than a new one; if it builds the controller inline, copy that block.

- [ ] **Step 2: Run the test to verify it fails**

```bash
$PY -m pytest tests/ui/test_review_controller.py -q
```

Expected: FAIL — no row labelled `w1 inductance`.

- [ ] **Step 3: Add the line**

In `src/inductor_designer/ui/review_controller.py`, after the existing
current-density `rows.extend(...)` block, add:

```python
        rows.extend(
            {
                "label": f"{row['windingId']} inductance",
                "text": str(row["inductance"]["text"]),  # type: ignore[index]
            }
            for row in winding_rows
        )
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
$PY -m pytest tests/ui/test_review_controller.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/ui/review_controller.py tests/ui/test_review_controller.py
git commit -m "feat(ui): list per-winding inductance on the Review screen"
```

---

### Task 7: Full verification

- [ ] **Step 1: Run the whole suite**

```bash
$PY -m pytest -n 8 -q
```

Expected: PASS, 0 failures. Baseline was 1161 passed, 7 skipped; the count
grows by the new tests and the skip count must not change.

- [ ] **Step 2: Lint and type-check**

```bash
$PY -m ruff check src tests && $PY -m ruff format --check src tests && $PY -m mypy src
```

Expected: no findings. Fix any line over 100 characters in the new module by
wrapping, not by widening the limit.

- [ ] **Step 3: Confirm the dependency boundary held**

```bash
grep -rn "PySide6\|pyaedt\|sqlite3" src/inductor_designer/simulation/
```

Expected: no output. `simulation` must import no Qt, PyAEDT, or SQLite.

- [ ] **Step 4: Look at the screen**

Launch the application, open a project with a catalog core, and check the
Preliminary screen: the Core summary shows the nine new rows and the winding
table shows an `Inductance` column. Confirm the `A_L` deviation is a plausible
roll-off (a powder core under bias reads negative), not a 900 % number that
would mean the area or the path length is being applied in the wrong place.

- [ ] **Step 5: Commit any fixes and report**

```bash
git add -A && git commit -m "test: verify preliminary inductance across the suite"
```

Report: changed files, the exact test counts, and anything left out.

---

## Notes for the implementer

- **Do not** add a mutual-inductance or coupling-factor row. The design
  excludes them deliberately: at this level of model `k = 1`, so they would
  state an assumption, not a result.
- **Do not** substitute the material record's `relative_permeability` as a
  reference for the `A_L` check. The catalog `A_L` is the single reference, by
  design, so the two reported permeabilities cannot contradict each other.
- **Do not** report a per-winding stored energy. The per-winding sum is wrong
  for coupled windings without a mutual term.
- A_L deviation renders without a leading `+` for positive values. That is
  accepted, not an oversight.
