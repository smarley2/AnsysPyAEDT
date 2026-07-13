# Foundation and Compatibility Spike Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish a tested Python project, versioned project-envelope schema, AEDT capability contracts, PyAEDT spike gateway, minimal Qt Quick 3D shell, CI, and a reproducible Commercial/Student compatibility record.

**Architecture:** Inner packages expose standard-library-only contracts for capability policy and AEDT requests. The PyAEDT and Qt dependencies remain optional outer adapters, while fakes exercise their contracts in hosted CI. Real-AEDT runs use the same gateway and write machine-readable evidence without committing generated AEDT projects.

**Tech Stack:** Python 3.10 baseline, Hatchling, pytest, pytest-cov, Ruff, mypy, JSON Schema 2020-12, PySide6/Qt Quick 3D, PyAEDT, GitHub Actions.

## Global Constraints

- Target platform: Windows.
- Minimum AEDT release: 2024 R2.
- Supported editions: Commercial and Student.
- The desktop application and AEDT extension must share the same core.
- Original code is Apache-2.0.
- Code, schemas, documentation, UI copy, logs, branches, commits, and pull requests are English.
- `domain`, `geometry`, `materials`, and solver-independent `simulation` code must not import PyAEDT, Qt, SQLite, or operating-system APIs.
- AEDT and PyAEDT version differences must remain behind adapter interfaces.
- Python 3.10 is the runtime baseline because AEDT 2023 R2 and newer include CPython 3.10; hosted CI also exercises Python 3.13.
- PyAEDT is optional and constrained to `>=0.27,<2`; the controlled compatibility spike, not the declared dependency range, decides whether a specific AEDT release/edition is supported.
- Never guess Student limits or undocumented solver capabilities; record observed evidence or report the capability as unknown.
- Do not commit generated `.aedt` projects, solver results, license details, credentials, or unrelated personal paths.
- Tests are written before implementation, and every task ends in an independently reviewable commit.

---

## Planned file map

| Path | Responsibility |
| --- | --- |
| `pyproject.toml` | Packaging, optional dependencies, test markers, coverage, Ruff, and mypy configuration |
| `src/inductor_designer/__about__.py` | Single source for the application version |
| `src/inductor_designer/{domain,geometry,materials,simulation}/` | Solver-independent inner packages |
| `src/inductor_designer/application/ports/aedt_gateway.py` | AEDT request/result DTOs and gateway protocol |
| `src/inductor_designer/adapters/pyaedt/gateway.py` | Lazy PyAEDT implementation of the gateway |
| `src/inductor_designer/adapters/persistence/schema_repository.py` | Loading and validating repository JSON schemas |
| `src/inductor_designer/ui/main.py` | Desktop shell launcher |
| `src/inductor_designer/ui/qml/Main.qml` | Minimal Guided Studio shell |
| `src/inductor_designer/ui/qml/PreviewPane.qml` | Qt Quick 3D preview smoke component |
| `schemas/project/v1.schema.json` | Version 1 project-envelope schema |
| `compatibility/aedt-matrix.yml` | Reviewed release/edition evidence; never inferred from version alone |
| `tools/check_architecture.py` | Static forbidden-import boundary check |
| `tools/aedt_spike.py` | CLI that runs the real 2D/3D gateway spike and writes evidence |
| `tools/run_aedt_spike.ps1` | Controlled Windows runner for one release/edition matrix row |
| `tests/` | Unit, architecture, contract, UI, and tagged real-AEDT tests |
| `.github/workflows/ci.yml` | Hosted non-AEDT quality and test matrix |
| `docs/development/aedt-compatibility-testing.md` | Operator checklist and evidence review procedure |

### Task 1: Package skeleton and quality configuration

**Owner:** Codex or Claude, one agent in a dedicated branch/worktree.

**Files:**
- Create: `pyproject.toml`
- Create: `src/inductor_designer/__init__.py`
- Create: `src/inductor_designer/__about__.py`
- Create: `src/inductor_designer/domain/__init__.py`
- Create: `src/inductor_designer/geometry/__init__.py`
- Create: `src/inductor_designer/materials/__init__.py`
- Create: `src/inductor_designer/simulation/__init__.py`
- Create: `src/inductor_designer/application/__init__.py`
- Create: `src/inductor_designer/adapters/__init__.py`
- Create: `tests/unit/test_package.py`

**Interfaces:**
- Consumes: No implementation interfaces.
- Produces: `inductor_designer.__version__: str`; editable extras `dev`, `ui`, and `aedt`.

- [ ] **Step 1: Write the failing package metadata test**

```python
# tests/unit/test_package.py
from importlib.metadata import version

import inductor_designer


def test_package_exposes_installed_version() -> None:
    assert inductor_designer.__version__ == version("pyaedt-inductor-designer")
    assert inductor_designer.__version__ == "0.1.0.dev0"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/unit/test_package.py -v`

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'inductor_designer'`.

- [ ] **Step 3: Add packaging and tool configuration**

```toml
# pyproject.toml
[build-system]
requires = ["hatchling>=1.27,<2"]
build-backend = "hatchling.build"

[project]
name = "pyaedt-inductor-designer"
dynamic = ["version"]
description = "Design inductors and generate Ansys Maxwell projects through PyAEDT."
readme = "README.md"
requires-python = ">=3.10,<3.14"
license = { file = "LICENSE" }
authors = [{ name = "PyAEDT Inductor Designer contributors" }]
dependencies = [
  "jsonschema>=4.23,<5",
  "packaging>=24.2,<26",
  "platformdirs>=4.3,<5",
]

[project.optional-dependencies]
ui = ["PySide6>=6.7,<7"]
aedt = ["pyaedt>=0.27,<2"]
dev = [
  "mypy>=1.13,<2",
  "pytest>=8.3,<9",
  "pytest-cov>=6,<8",
  "ruff>=0.9,<1",
  "types-jsonschema>=4.23,<5",
  "PyYAML>=6.0,<7",
]

[project.scripts]
inductor-designer = "inductor_designer.ui.main:main"

[tool.hatch.version]
path = "src/inductor_designer/__about__.py"

[tool.hatch.build.targets.wheel]
packages = ["src/inductor_designer"]

[tool.pytest.ini_options]
addopts = "--strict-markers --strict-config"
testpaths = ["tests"]
markers = [
  "aedt: requires a controlled licensed AEDT installation",
  "ui: requires the PySide6 UI extra",
]

[tool.coverage.run]
branch = true
source = ["inductor_designer"]

[tool.coverage.report]
fail_under = 80
show_missing = true

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "ANN", "SIM"]

[tool.mypy]
python_version = "3.10"
strict = true
packages = ["inductor_designer"]

[[tool.mypy.overrides]]
module = ["ansys.aedt.*", "PySide6.*"]
ignore_missing_imports = true
```

```python
# src/inductor_designer/__about__.py
__version__ = "0.1.0.dev0"
```

```python
# src/inductor_designer/__init__.py
from inductor_designer.__about__ import __version__

__all__ = ["__version__"]
```

Create each listed package `__init__.py` with this exact content:

```python
"""Package boundary; public interfaces are exported explicitly by feature modules."""
```

- [ ] **Step 4: Install the development environment and run the test**

Run: `python -m pip install -e ".[dev]"`

Expected: exit code 0 and an editable `pyaedt-inductor-designer` installation.

Run: `python -m pytest tests/unit/test_package.py -v`

Expected: `1 passed`.

- [ ] **Step 5: Run initial static checks**

Run: `python -m ruff check .`

Expected: `All checks passed!`

Run: `python -m mypy src`

Expected: `Success: no issues found`.

- [ ] **Step 6: Commit**

```powershell
git add pyproject.toml src tests/unit/test_package.py
git commit -m "build: establish Python package and quality gates"
```

### Task 2: Enforce dependency boundaries

**Owner:** Codex or Claude.

**Files:**
- Create: `tools/__init__.py`
- Create: `tools/check_architecture.py`
- Create: `tests/architecture/test_dependency_boundaries.py`

**Interfaces:**
- Consumes: Package roots created in Task 1.
- Produces: `find_forbidden_imports(source_root: Path) -> tuple[Violation, ...]` and a zero/non-zero CLI exit code.

- [ ] **Step 1: Write failing checker tests**

```python
# tests/architecture/test_dependency_boundaries.py
from pathlib import Path

from tools.check_architecture import Violation, find_forbidden_imports


def test_finds_forbidden_dependency_in_inner_package(tmp_path: Path) -> None:
    source = tmp_path / "inductor_designer" / "domain" / "model.py"
    source.parent.mkdir(parents=True)
    source.write_text("from ansys.aedt.core import Maxwell3d\n", encoding="utf-8")

    assert find_forbidden_imports(tmp_path) == (
        Violation(source, 1, "ansys.aedt.core", "domain"),
    )


def test_repository_inner_packages_respect_boundaries() -> None:
    assert find_forbidden_imports(Path("src")) == ()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/architecture/test_dependency_boundaries.py -v`

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'tools.check_architecture'`.

- [ ] **Step 3: Implement the AST boundary checker**

```python
# tools/__init__.py
"""Repository development tools."""
```

```python
# tools/check_architecture.py
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

INNER_PACKAGES = frozenset({"domain", "geometry", "materials", "simulation"})
FORBIDDEN_ROOTS = frozenset({"ansys", "pyaedt", "PySide6", "sqlite3", "os", "platform"})


@dataclass(frozen=True, slots=True)
class Violation:
    path: Path
    line: int
    imported: str
    inner_package: str


def _imported_names(node: ast.Import | ast.ImportFrom) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(alias.name for alias in node.names)
    return (node.module or "",)


def find_forbidden_imports(source_root: Path) -> tuple[Violation, ...]:
    violations: list[Violation] = []
    package_root = source_root / "inductor_designer"
    for inner_package in sorted(INNER_PACKAGES):
        for path in sorted((package_root / inner_package).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.Import, ast.ImportFrom)):
                    continue
                for imported in _imported_names(node):
                    if imported.split(".", maxsplit=1)[0] in FORBIDDEN_ROOTS:
                        violations.append(
                            Violation(path, node.lineno, imported, inner_package)
                        )
    return tuple(violations)


def main() -> int:
    violations = find_forbidden_imports(Path("src"))
    for item in violations:
        print(f"{item.path}:{item.line}: {item.inner_package} imports {item.imported}")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Verify checker behavior**

Run: `python -m pytest tests/architecture/test_dependency_boundaries.py -v`

Expected: `2 passed`.

Run: `python -m tools.check_architecture`

Expected: no output and exit code 0.

- [ ] **Step 5: Commit**

```powershell
git add tools tests/architecture
git commit -m "test: enforce inner package dependency boundaries"
```

### Task 3: Versioned project-envelope schema repository

**Owner:** Codex or Claude.

**Files:**
- Create: `schemas/project/v1.schema.json`
- Create: `src/inductor_designer/adapters/persistence/__init__.py`
- Create: `src/inductor_designer/adapters/persistence/schema_repository.py`
- Create: `tests/unit/adapters/persistence/test_schema_repository.py`
- Create: `tests/fixtures/projects/minimal-v1.inductor.json`

**Interfaces:**
- Consumes: `jsonschema` runtime dependency from Task 1.
- Produces: `SchemaRepository(root: Path)`, `load_project_schema(version: int) -> Mapping[str, object]`, and `validate_project(document: Mapping[str, object]) -> None`.

- [ ] **Step 1: Write schema repository tests**

```python
# tests/unit/adapters/persistence/test_schema_repository.py
import json
from pathlib import Path

import pytest
from jsonschema.exceptions import ValidationError

from inductor_designer.adapters.persistence.schema_repository import SchemaRepository


def test_minimal_v1_project_is_valid() -> None:
    document = json.loads(
        Path("tests/fixtures/projects/minimal-v1.inductor.json").read_text(encoding="utf-8")
    )
    SchemaRepository(Path("schemas")).validate_project(document)


def test_unknown_project_version_is_rejected() -> None:
    repository = SchemaRepository(Path("schemas"))

    with pytest.raises(ValueError, match="Unsupported project schema version: 99"):
        repository.validate_project({"schemaVersion": 99})


def test_missing_project_identifier_is_rejected() -> None:
    repository = SchemaRepository(Path("schemas"))

    with pytest.raises(ValidationError):
        repository.validate_project(
            {
                "schemaVersion": 1,
                "metadata": {"name": "Missing identifier"},
                "target": {"aedtRelease": "2024.2", "edition": "commercial"},
            }
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/adapters/persistence/test_schema_repository.py -v`

Expected: FAIL during collection because `schema_repository` does not exist.

- [ ] **Step 3: Add the version 1 envelope schema and fixture**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://github.com/smarley2/AnsysPyAEDT/schemas/project/v1.schema.json",
  "title": "PyAEDT Inductor Designer project envelope v1",
  "type": "object",
  "additionalProperties": false,
  "required": ["schemaVersion", "projectId", "metadata", "target"],
  "properties": {
    "schemaVersion": { "const": 1 },
    "projectId": { "type": "string", "format": "uuid" },
    "metadata": {
      "type": "object",
      "additionalProperties": false,
      "required": ["name"],
      "properties": {
        "name": { "type": "string", "minLength": 1 },
        "description": { "type": "string", "default": "" }
      }
    },
    "target": {
      "type": "object",
      "additionalProperties": false,
      "required": ["aedtRelease", "edition"],
      "properties": {
        "aedtRelease": { "type": "string", "pattern": "^20[2-9][0-9]\\.[12]$" },
        "edition": { "enum": ["commercial", "student"] }
      }
    }
  }
}
```

```json
{
  "schemaVersion": 1,
  "projectId": "87da0e28-2018-4fa5-bba7-a24e9b8de6ce",
  "metadata": {
    "name": "Minimal compatibility project",
    "description": "Foundation fixture without inductor-domain fields."
  },
  "target": {
    "aedtRelease": "2024.2",
    "edition": "commercial"
  }
}
```

- [ ] **Step 4: Implement schema loading and validation**

```python
# src/inductor_designer/adapters/persistence/__init__.py
"""Persistence adapters."""
```

```python
# src/inductor_designer/adapters/persistence/schema_repository.py
from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


class SchemaRepository:
    def __init__(self, root: Path) -> None:
        self._root = root

    def load_project_schema(self, version: int) -> Mapping[str, object]:
        path = self._root / "project" / f"v{version}.schema.json"
        if not path.is_file():
            raise ValueError(f"Unsupported project schema version: {version}")
        loaded: Any = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError(f"Project schema is not a JSON object: {path}")
        return loaded

    def validate_project(self, document: Mapping[str, object]) -> None:
        version = document.get("schemaVersion")
        if not isinstance(version, int):
            raise ValueError("Project schemaVersion must be an integer")
        schema = self.load_project_schema(version)
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(document)
```

- [ ] **Step 5: Verify schema behavior**

Run: `python -m pytest tests/unit/adapters/persistence/test_schema_repository.py -v`

Expected: `3 passed`.

- [ ] **Step 6: Commit**

```powershell
git add schemas src/inductor_designer/adapters/persistence tests/unit/adapters/persistence tests/fixtures/projects
git commit -m "feat: add versioned project envelope schema"
```

### Task 4: Solver-independent AEDT capability policy

**Owner:** Codex or Claude.

**Files:**
- Create: `src/inductor_designer/simulation/capabilities.py`
- Create: `tests/unit/simulation/test_capabilities.py`

**Interfaces:**
- Consumes: Standard library only.
- Produces: `AedtRelease.parse(str)`, `CapabilitySnapshot`, `DcBiasStrategy`, and `select_dc_bias_strategy(snapshot, dimension) -> DcBiasDecision`.

- [ ] **Step 1: Write failing policy tests**

```python
# tests/unit/simulation/test_capabilities.py
import pytest

from inductor_designer.simulation.capabilities import (
    AedtEdition,
    AedtRelease,
    CapabilitySnapshot,
    DcBiasStrategy,
    ModelDimension,
    select_dc_bias_strategy,
)


def snapshot(release: str, include_dc_fields: bool) -> CapabilitySnapshot:
    return CapabilitySnapshot(
        release=AedtRelease.parse(release),
        edition=AedtEdition.COMMERCIAL,
        include_dc_fields_3d=include_dc_fields,
        discovered_limits=(),
        evidence_source="controlled-spike",
    )


def test_2025_r1_3d_uses_native_dc_fields_when_observed() -> None:
    decision = select_dc_bias_strategy(snapshot("2025.1", True), ModelDimension.THREE_D)
    assert decision.strategy is DcBiasStrategy.NATIVE_INCLUDE_DC_FIELDS
    assert decision.approximate is False


def test_2024_r2_3d_uses_documented_incremental_fallback() -> None:
    decision = select_dc_bias_strategy(snapshot("2024.2", False), ModelDimension.THREE_D)
    assert decision.strategy is DcBiasStrategy.MAGNETOSTATIC_INCREMENTAL_FALLBACK
    assert decision.approximate is True


def test_2d_dc_bias_is_blocked_until_a_supported_policy_exists() -> None:
    decision = select_dc_bias_strategy(snapshot("2026.1", True), ModelDimension.TWO_D)
    assert decision.strategy is DcBiasStrategy.BLOCKED
    assert "Maxwell 2D" in decision.reason


def test_unknown_3d_capability_is_blocked_instead_of_guessed() -> None:
    capabilities = CapabilitySnapshot(
        release=AedtRelease.parse("2026.1"),
        edition=AedtEdition.STUDENT,
        include_dc_fields_3d=None,
        discovered_limits=(),
        evidence_source="trivial-design-spike",
    )

    decision = select_dc_bias_strategy(capabilities, ModelDimension.THREE_D)

    assert decision.strategy is DcBiasStrategy.BLOCKED
    assert "not been reviewed" in decision.reason


def test_native_flag_before_2025_r1_is_rejected_as_inconsistent_evidence() -> None:
    with pytest.raises(ValueError, match="Include DC Fields cannot be recorded before 2025 R1"):
        snapshot("2024.2", True)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/simulation/test_capabilities.py -v`

Expected: FAIL during collection because `simulation.capabilities` does not exist.

- [ ] **Step 3: Implement immutable capability types and policy**

```python
# src/inductor_designer/simulation/capabilities.py
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True, order=True, slots=True)
class AedtRelease:
    year: int
    release: int

    @classmethod
    def parse(cls, value: str) -> "AedtRelease":
        parts = value.split(".")
        if len(parts) != 2 or not all(part.isdigit() for part in parts):
            raise ValueError(f"Invalid AEDT release: {value}")
        parsed = cls(int(parts[0]), int(parts[1]))
        if parsed.year < 2022 or parsed.release not in (1, 2):
            raise ValueError(f"Invalid AEDT release: {value}")
        return parsed

    def __str__(self) -> str:
        return f"{self.year}.{self.release}"


class AedtEdition(str, Enum):
    COMMERCIAL = "commercial"
    STUDENT = "student"


class ModelDimension(str, Enum):
    TWO_D = "2d"
    THREE_D = "3d"


class DcBiasStrategy(str, Enum):
    NATIVE_INCLUDE_DC_FIELDS = "native-include-dc-fields"
    MAGNETOSTATIC_INCREMENTAL_FALLBACK = "magnetostatic-incremental-fallback"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class CapabilitySnapshot:
    release: AedtRelease
    edition: AedtEdition
    include_dc_fields_3d: bool | None
    discovered_limits: tuple[str, ...]
    evidence_source: str

    def __post_init__(self) -> None:
        if self.include_dc_fields_3d and self.release < AedtRelease(2025, 1):
            raise ValueError("Include DC Fields cannot be recorded before 2025 R1")
        if not self.evidence_source.strip():
            raise ValueError("Capability evidence_source cannot be empty")


@dataclass(frozen=True, slots=True)
class DcBiasDecision:
    strategy: DcBiasStrategy
    approximate: bool
    reason: str


def select_dc_bias_strategy(
    capabilities: CapabilitySnapshot,
    dimension: ModelDimension,
) -> DcBiasDecision:
    if dimension is ModelDimension.TWO_D:
        return DcBiasDecision(
            DcBiasStrategy.BLOCKED,
            False,
            "Maxwell 2D DC-bias generation is blocked until a validated policy is available.",
        )
    if capabilities.include_dc_fields_3d:
        return DcBiasDecision(
            DcBiasStrategy.NATIVE_INCLUDE_DC_FIELDS,
            False,
            "The controlled capability record confirms native 3D Include DC Fields.",
        )
    if capabilities.include_dc_fields_3d is None:
        return DcBiasDecision(
            DcBiasStrategy.BLOCKED,
            False,
            "The 3D Include DC Fields capability has not been reviewed for this environment.",
        )
    return DcBiasDecision(
        DcBiasStrategy.MAGNETOSTATIC_INCREMENTAL_FALLBACK,
        True,
        "Use the documented Magnetostatic operating-point and incremental-linearization approximation.",
    )
```

- [ ] **Step 4: Verify capability policy and dependency boundary**

Run: `python -m pytest tests/unit/simulation/test_capabilities.py -v`

Expected: `5 passed`.

Run: `python -m tools.check_architecture`

Expected: no output and exit code 0.

- [ ] **Step 5: Commit**

```powershell
git add src/inductor_designer/simulation/capabilities.py tests/unit/simulation/test_capabilities.py
git commit -m "feat: define solver-independent AEDT capability policy"
```

### Task 5: AEDT gateway contract and recording fake

**Owner:** Codex or Claude.

**Files:**
- Create: `src/inductor_designer/application/ports/__init__.py`
- Create: `src/inductor_designer/application/ports/aedt_gateway.py`
- Create: `tests/fakes/__init__.py`
- Create: `tests/fakes/aedt_gateway.py`
- Create: `tests/contract/test_aedt_gateway_contract.py`

**Interfaces:**
- Consumes: `AedtRelease`, `AedtEdition`, and `ModelDimension` from Task 4.
- Produces: `AedtGateway` protocol, `AedtProbeRequest`, `AedtProbeResult`, `ProbeArtifact`, and `RecordingAedtGateway`.

- [ ] **Step 1: Write the gateway contract test**

```python
# tests/contract/test_aedt_gateway_contract.py
from pathlib import Path

from inductor_designer.application.ports.aedt_gateway import AedtProbeRequest
from inductor_designer.simulation.capabilities import AedtEdition, AedtRelease
from tests.fakes.aedt_gateway import RecordingAedtGateway


def test_recording_gateway_returns_both_dimensions_in_stable_order(tmp_path: Path) -> None:
    request = AedtProbeRequest(
        release=AedtRelease.parse("2024.2"),
        edition=AedtEdition.STUDENT,
        non_graphical=False,
        output_directory=tmp_path,
    )
    gateway = RecordingAedtGateway()

    result = gateway.run_probe(request)

    assert gateway.requests == [request]
    assert [artifact.dimension.value for artifact in result.artifacts] == ["2d", "3d"]
    assert all(artifact.created and artifact.saved for artifact in result.artifacts)
    assert result.release == request.release
    assert result.edition == request.edition
```

- [ ] **Step 2: Run the contract test to verify it fails**

Run: `python -m pytest tests/contract/test_aedt_gateway_contract.py -v`

Expected: FAIL during collection because `application.ports.aedt_gateway` does not exist.

- [ ] **Step 3: Define the gateway DTOs and protocol**

```python
# src/inductor_designer/application/ports/__init__.py
"""Application ports implemented by infrastructure adapters."""
```

```python
# src/inductor_designer/application/ports/aedt_gateway.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from inductor_designer.simulation.capabilities import (
    AedtEdition,
    AedtRelease,
    CapabilitySnapshot,
    ModelDimension,
)


@dataclass(frozen=True, slots=True)
class AedtProbeRequest:
    release: AedtRelease
    edition: AedtEdition
    non_graphical: bool
    output_directory: Path


@dataclass(frozen=True, slots=True)
class ProbeArtifact:
    dimension: ModelDimension
    project_path: Path
    created: bool
    saved: bool
    message: str


@dataclass(frozen=True, slots=True)
class AedtProbeResult:
    release: AedtRelease
    edition: AedtEdition
    pyaedt_version: str
    capabilities: CapabilitySnapshot
    artifacts: tuple[ProbeArtifact, ...]


class AedtGateway(Protocol):
    def run_probe(self, request: AedtProbeRequest) -> AedtProbeResult: ...
```

- [ ] **Step 4: Implement the deterministic recording fake**

```python
# tests/fakes/__init__.py
"""Test doubles shared by contract tests."""
```

```python
# tests/fakes/aedt_gateway.py
from pathlib import Path

from inductor_designer.application.ports.aedt_gateway import (
    AedtProbeRequest,
    AedtProbeResult,
    ProbeArtifact,
)
from inductor_designer.simulation.capabilities import CapabilitySnapshot, ModelDimension


class RecordingAedtGateway:
    def __init__(self) -> None:
        self.requests: list[AedtProbeRequest] = []

    def run_probe(self, request: AedtProbeRequest) -> AedtProbeResult:
        self.requests.append(request)
        artifacts = tuple(
            ProbeArtifact(
                dimension=dimension,
                project_path=Path(request.output_directory) / f"probe-{dimension.value}.aedt",
                created=True,
                saved=True,
                message="recorded without launching AEDT",
            )
            for dimension in (ModelDimension.TWO_D, ModelDimension.THREE_D)
        )
        return AedtProbeResult(
            release=request.release,
            edition=request.edition,
            pyaedt_version="recording-fake",
            capabilities=CapabilitySnapshot(
                release=request.release,
                edition=request.edition,
                include_dc_fields_3d=None,
                discovered_limits=(),
                evidence_source="recording-fake",
            ),
            artifacts=artifacts,
        )
```

- [ ] **Step 5: Verify the gateway contract**

Run: `python -m pytest tests/contract/test_aedt_gateway_contract.py -v`

Expected: `1 passed`.

- [ ] **Step 6: Commit**

```powershell
git add src/inductor_designer/application/ports tests/fakes tests/contract
git commit -m "feat: define AEDT gateway contract and recording fake"
```

### Task 6: Lazy PyAEDT adapter and trivial Maxwell designs

**Owner:** Codex or Claude on a Windows machine; hosted tests use an injected fake factory.

**Files:**
- Create: `src/inductor_designer/adapters/pyaedt/__init__.py`
- Create: `src/inductor_designer/adapters/pyaedt/gateway.py`
- Create: `tests/unit/adapters/pyaedt/test_gateway.py`
- Create: `tests/integration/aedt/test_trivial_design.py`

**Interfaces:**
- Consumes: `AedtGateway` DTOs from Task 5.
- Produces: `PyaedtGateway(app_factory: MaxwellAppFactory | None = None)` implementing `run_probe()`; PyAEDT imports occur only inside the default factory.

- [ ] **Step 1: Write adapter tests using fake Maxwell applications**

```python
# tests/unit/adapters/pyaedt/test_gateway.py
from pathlib import Path
from typing import Any

from inductor_designer.adapters.pyaedt.gateway import PyaedtGateway
from inductor_designer.application.ports.aedt_gateway import AedtProbeRequest
from inductor_designer.simulation.capabilities import AedtEdition, AedtRelease


class FakeModeler:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def create_rectangle(self, *args: Any, **kwargs: Any) -> object:
        self.calls.append(("create_rectangle", args, kwargs))
        return object()

    def create_box(self, *args: Any, **kwargs: Any) -> object:
        self.calls.append(("create_box", args, kwargs))
        return object()


class FakeApp:
    def __init__(self) -> None:
        self.modeler = FakeModeler()
        self.saved_paths: list[str] = []
        self.released = False

    def save_project(self, path: str) -> bool:
        self.saved_paths.append(path)
        return True

    def release_desktop(self, close_projects: bool, close_desktop: bool) -> None:
        assert close_projects and close_desktop
        self.released = True


class FakeFactory:
    pyaedt_version = "test-version"

    def __init__(self) -> None:
        self.apps: list[tuple[str, dict[str, object], FakeApp]] = []

    def create(self, dimension: str, **kwargs: object) -> FakeApp:
        app = FakeApp()
        self.apps.append((dimension, kwargs, app))
        return app


def test_probe_creates_and_saves_2d_and_3d_projects(tmp_path: Path) -> None:
    factory = FakeFactory()
    gateway = PyaedtGateway(factory)
    request = AedtProbeRequest(
        release=AedtRelease.parse("2024.2"),
        edition=AedtEdition.STUDENT,
        non_graphical=False,
        output_directory=tmp_path,
    )

    result = gateway.run_probe(request)

    assert [entry[0] for entry in factory.apps] == ["2d", "3d"]
    assert all(entry[1]["student_version"] is True for entry in factory.apps)
    assert factory.apps[0][2].modeler.calls[0][0] == "create_rectangle"
    assert factory.apps[1][2].modeler.calls[0][0] == "create_box"
    assert all(app.released for _, _, app in factory.apps)
    assert all(artifact.saved for artifact in result.artifacts)
    assert result.capabilities.include_dc_fields_3d is None
```

- [ ] **Step 2: Run the adapter test to verify it fails**

Run: `python -m pytest tests/unit/adapters/pyaedt/test_gateway.py -v`

Expected: FAIL during collection because `adapters.pyaedt.gateway` does not exist.

- [ ] **Step 3: Implement the lazy factory and adapter**

```python
# src/inductor_designer/adapters/pyaedt/__init__.py
"""PyAEDT infrastructure adapter."""
```

```python
# src/inductor_designer/adapters/pyaedt/gateway.py
from __future__ import annotations

from importlib.metadata import version
from pathlib import Path
from typing import Any, Protocol

from inductor_designer.application.ports.aedt_gateway import (
    AedtProbeRequest,
    AedtProbeResult,
    ProbeArtifact,
)
from inductor_designer.simulation.capabilities import CapabilitySnapshot, ModelDimension


class MaxwellApp(Protocol):
    modeler: Any

    def save_project(self, path: str) -> bool: ...

    def release_desktop(self, close_projects: bool, close_desktop: bool) -> None: ...


class MaxwellAppFactory(Protocol):
    pyaedt_version: str

    def create(self, dimension: str, **kwargs: object) -> MaxwellApp: ...


class DefaultMaxwellAppFactory:
    @property
    def pyaedt_version(self) -> str:
        return version("pyaedt")

    def create(self, dimension: str, **kwargs: object) -> MaxwellApp:
        from ansys.aedt.core import Maxwell2d, Maxwell3d

        app_class = Maxwell2d if dimension == "2d" else Maxwell3d
        return app_class(**kwargs)


class PyaedtGateway:
    def __init__(self, app_factory: MaxwellAppFactory | None = None) -> None:
        self._factory = app_factory or DefaultMaxwellAppFactory()

    def run_probe(self, request: AedtProbeRequest) -> AedtProbeResult:
        request.output_directory.mkdir(parents=True, exist_ok=True)
        artifacts = (
            self._create_design(request, ModelDimension.TWO_D),
            self._create_design(request, ModelDimension.THREE_D),
        )
        return AedtProbeResult(
            release=request.release,
            edition=request.edition,
            pyaedt_version=self._factory.pyaedt_version,
            capabilities=CapabilitySnapshot(
                release=request.release,
                edition=request.edition,
                include_dc_fields_3d=None,
                discovered_limits=(),
                evidence_source="trivial-design-spike",
            ),
            artifacts=artifacts,
        )

    def _create_design(
        self,
        request: AedtProbeRequest,
        dimension: ModelDimension,
    ) -> ProbeArtifact:
        project_path = request.output_directory / f"probe-{dimension.value}.aedt"
        app = self._factory.create(
            dimension.value,
            project=str(project_path),
            design=f"CompatibilityProbe{dimension.value.upper()}",
            solution_type="Magnetostatic",
            version=str(request.release),
            non_graphical=request.non_graphical,
            new_desktop=True,
            close_on_exit=False,
            student_version=request.edition.value == "student",
        )
        try:
            if dimension is ModelDimension.TWO_D:
                app.modeler.create_rectangle(
                    origin=["0mm", "0mm", "0mm"],
                    sizes=["10mm", "5mm"],
                    name="CompatibilityProbeRectangle",
                )
            else:
                app.modeler.create_box(
                    origin=["0mm", "0mm", "0mm"],
                    sizes=["10mm", "5mm", "2mm"],
                    name="CompatibilityProbeBox",
                )
            saved = bool(app.save_project(str(project_path)))
            return ProbeArtifact(
                dimension=dimension,
                project_path=project_path,
                created=True,
                saved=saved,
                message="Trivial Maxwell design created and save requested.",
            )
        finally:
            app.release_desktop(close_projects=True, close_desktop=True)
```

- [ ] **Step 4: Verify adapter behavior without AEDT**

Run: `python -m pytest tests/unit/adapters/pyaedt/test_gateway.py -v`

Expected: `1 passed`; PyAEDT and AEDT are not imported or launched.

Run: `python -m pytest tests/contract tests/unit/adapters/pyaedt -v`

Expected: `2 passed`.

- [ ] **Step 5: Add the tagged real-AEDT integration test**

```python
# tests/integration/aedt/test_trivial_design.py
import os
from pathlib import Path

import pytest

from inductor_designer.adapters.pyaedt.gateway import PyaedtGateway
from inductor_designer.application.ports.aedt_gateway import AedtProbeRequest
from inductor_designer.simulation.capabilities import AedtEdition, AedtRelease


@pytest.mark.aedt
def test_real_aedt_creates_and_saves_both_dimensions(tmp_path: Path) -> None:
    release = os.environ.get("INDUCTOR_AEDT_RELEASE")
    edition = os.environ.get("INDUCTOR_AEDT_EDITION")
    if release is None or edition is None:
        pytest.skip("Set INDUCTOR_AEDT_RELEASE and INDUCTOR_AEDT_EDITION")

    result = PyaedtGateway().run_probe(
        AedtProbeRequest(
            release=AedtRelease.parse(release),
            edition=AedtEdition(edition),
            non_graphical=False,
            output_directory=tmp_path,
        )
    )

    assert [artifact.created for artifact in result.artifacts] == [True, True]
    assert [artifact.saved for artifact in result.artifacts] == [True, True]
```

Run: `python -m pytest -m "not aedt" tests/integration/aedt/test_trivial_design.py -v`

Expected: `1 deselected`; hosted checks never launch AEDT.

- [ ] **Step 6: Commit**

```powershell
git add src/inductor_designer/adapters/pyaedt tests/unit/adapters/pyaedt tests/integration/aedt
git commit -m "feat: add lazy PyAEDT compatibility gateway"
```

### Task 7: Machine-readable compatibility spike CLI

**Owner:** Codex or Claude; the unit test uses the recording gateway.

**Files:**
- Create: `tools/aedt_spike.py`
- Create: `tests/unit/tools/test_aedt_spike.py`

**Interfaces:**
- Consumes: `AedtGateway` from Task 5 and `PyaedtGateway` from Task 6.
- Produces: `run_spike(gateway, request, evidence_path) -> dict[str, object]` and `python -m tools.aedt_spike`.

- [ ] **Step 1: Write the evidence serialization test**

```python
# tests/unit/tools/test_aedt_spike.py
import json
from pathlib import Path

from inductor_designer.application.ports.aedt_gateway import AedtProbeRequest
from inductor_designer.simulation.capabilities import AedtEdition, AedtRelease
from tests.fakes.aedt_gateway import RecordingAedtGateway
from tools.aedt_spike import run_spike


def test_run_spike_writes_reviewable_evidence(tmp_path: Path) -> None:
    evidence_path = tmp_path / "evidence.json"
    request = AedtProbeRequest(
        release=AedtRelease.parse("2024.2"),
        edition=AedtEdition.COMMERCIAL,
        non_graphical=True,
        output_directory=tmp_path / "projects",
    )

    evidence = run_spike(RecordingAedtGateway(), request, evidence_path)

    assert evidence["aedtRelease"] == "2024.2"
    assert evidence["edition"] == "commercial"
    assert [item["dimension"] for item in evidence["artifacts"]] == ["2d", "3d"]
    assert json.loads(evidence_path.read_text(encoding="utf-8")) == evidence
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/unit/tools/test_aedt_spike.py -v`

Expected: FAIL during collection because `tools.aedt_spike` does not exist.

- [ ] **Step 3: Implement serialization and CLI argument handling**

```python
# tools/aedt_spike.py
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from inductor_designer.adapters.pyaedt.gateway import PyaedtGateway
from inductor_designer.application.ports.aedt_gateway import AedtGateway, AedtProbeRequest
from inductor_designer.simulation.capabilities import AedtEdition, AedtRelease


def run_spike(
    gateway: AedtGateway,
    request: AedtProbeRequest,
    evidence_path: Path,
) -> dict[str, Any]:
    result = gateway.run_probe(request)
    evidence: dict[str, Any] = {
        "schemaVersion": 1,
        "aedtRelease": str(result.release),
        "edition": result.edition.value,
        "pyaedtVersion": result.pyaedt_version,
        "capabilities": {
            "includeDcFields3d": result.capabilities.include_dc_fields_3d,
            "discoveredLimits": list(result.capabilities.discovered_limits),
            "evidenceSource": result.capabilities.evidence_source,
        },
        "artifacts": [
            {
                "dimension": artifact.dimension.value,
                "projectPath": artifact.project_path.name,
                "created": artifact.created,
                "saved": artifact.saved,
                "message": artifact.message,
            }
            for artifact in result.artifacts
        ],
    }
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    return evidence


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the controlled AEDT compatibility spike.")
    parser.add_argument("--release", required=True, help="AEDT release such as 2024.2")
    parser.add_argument("--edition", required=True, choices=["commercial", "student"])
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--graphical", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    request = AedtProbeRequest(
        release=AedtRelease.parse(args.release),
        edition=AedtEdition(args.edition),
        non_graphical=not args.graphical,
        output_directory=args.output_directory,
    )
    evidence = run_spike(PyaedtGateway(), request, args.evidence)
    return 0 if all(item["saved"] for item in evidence["artifacts"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Verify deterministic evidence output**

Run: `python -m pytest tests/unit/tools/test_aedt_spike.py -v`

Expected: `1 passed`.

- [ ] **Step 5: Commit**

```powershell
git add tools/aedt_spike.py tests/unit/tools/test_aedt_spike.py
git commit -m "feat: add machine-readable AEDT spike runner"
```

### Task 8: Minimal Guided Studio and Qt Quick 3D smoke test

**Owner:** Codex or Claude.

**Files:**
- Create: `src/inductor_designer/ui/__init__.py`
- Create: `src/inductor_designer/ui/main.py`
- Create: `src/inductor_designer/ui/qml/Main.qml`
- Create: `src/inductor_designer/ui/qml/PreviewPane.qml`
- Create: `tests/ui/test_qml_smoke.py`

**Interfaces:**
- Consumes: `PySide6>=6.7,<7` from the `ui` extra.
- Produces: `qml_directory() -> Path`, `create_engine() -> QQmlApplicationEngine`, and the `inductor-designer` shell entry point.

- [ ] **Step 1: Write the offscreen QML load test**

```python
# tests/ui/test_qml_smoke.py
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QSG_RHI_BACKEND", "software")

pytest.importorskip("PySide6")

from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.ui.main import create_engine  # noqa: E402


@pytest.mark.ui
def test_guided_studio_qml_loads() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = create_engine()

    assert app is not None
    assert len(engine.rootObjects()) == 1
```

- [ ] **Step 2: Install the UI extra and verify the test fails**

Run: `python -m pip install -e ".[dev,ui]"`

Expected: exit code 0.

Run: `python -m pytest tests/ui/test_qml_smoke.py -v`

Expected: FAIL during collection because `inductor_designer.ui.main` does not exist.

- [ ] **Step 3: Implement the QML launcher**

```python
# src/inductor_designer/ui/__init__.py
"""Desktop user interface shell."""
```

```python
# src/inductor_designer/ui/main.py
from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtQml import QQmlApplicationEngine


def qml_directory() -> Path:
    return Path(__file__).with_name("qml")


def create_engine() -> "QQmlApplicationEngine":
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlApplicationEngine

    engine = QQmlApplicationEngine()
    engine.load(QUrl.fromLocalFile(str(qml_directory() / "Main.qml")))
    return engine


def main() -> int:
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication(sys.argv)
    engine = create_engine()
    if not engine.rootObjects():
        return 1
    return app.exec()
```

- [ ] **Step 4: Add the minimal Guided Studio QML**

```qml
// src/inductor_designer/ui/qml/Main.qml
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: window
    width: 1200
    height: 760
    visible: true
    title: qsTr("PyAEDT Inductor Designer")

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Frame {
            Layout.preferredWidth: 320
            Layout.fillHeight: true
            ColumnLayout {
                anchors.fill: parent
                Label { text: qsTr("Core") }
                Label { text: qsTr("Windings") }
                Label { text: qsTr("Materials") }
                Label { text: qsTr("Simulation") }
                Label { text: qsTr("Review") }
                Item { Layout.fillHeight: true }
                Label { text: qsTr("Foundation preview spike") }
            }
        }

        PreviewPane {
            Layout.fillWidth: true
            Layout.fillHeight: true
        }
    }
}
```

```qml
// src/inductor_designer/ui/qml/PreviewPane.qml
import QtQuick
import QtQuick3D

Rectangle {
    color: "#111827"

    View3D {
        anchors.fill: parent
        environment: SceneEnvironment {
            clearColor: "#111827"
            backgroundMode: SceneEnvironment.Color
        }

        PerspectiveCamera { z: 450 }
        DirectionalLight { eulerRotation.x: -35; eulerRotation.y: -30 }
        Model {
            source: "#Cylinder"
            scale: Qt.vector3d(1.8, 0.45, 1.8)
            eulerRotation.x: 68
            materials: PrincipledMaterial {
                baseColor: "#334155"
                metalness: 0.1
                roughness: 0.65
            }
        }
        Model {
            source: "#Cylinder"
            x: 120
            scale: Qt.vector3d(0.12, 1.1, 0.12)
            eulerRotation.x: 68
            materials: PrincipledMaterial { baseColor: "#d97706" }
        }
    }
}
```

- [ ] **Step 5: Ensure QML ships in wheels**

Add to `pyproject.toml`:

```toml
[tool.hatch.build.targets.wheel.force-include]
"src/inductor_designer/ui/qml" = "inductor_designer/ui/qml"
```

- [ ] **Step 6: Verify the UI smoke test and launcher**

Run: `python -m pytest tests/ui/test_qml_smoke.py -v`

Expected: `1 passed`; the test creates no visible window.

Run: `python -m ruff check src/inductor_designer/ui tests/ui`

Expected: `All checks passed!`. The imports after Qt environment setup carry `# noqa: E402` because those variables must be set before importing PySide6.

- [ ] **Step 7: Commit**

```powershell
git add pyproject.toml src/inductor_designer/ui tests/ui
git commit -m "feat: add Guided Studio Qt Quick 3D smoke shell"
```

### Task 9: Hosted non-AEDT CI

**Owner:** Codex or Claude.

**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: `README.md`

**Interfaces:**
- Consumes: Test markers and quality configuration from Task 1.
- Produces: Windows/Linux checks on Python 3.10 and 3.13 without requiring AEDT or an Ansys license.

- [ ] **Step 1: Run the complete hosted-equivalent checks locally**

Run: `python -m ruff check .`

Expected: `All checks passed!`.

Run: `python -m mypy src tools`

Expected: `Success: no issues found`.

Run: `python -m pytest -m "not aedt" --cov=inductor_designer --cov-report=term-missing`

Expected: all tests pass and total coverage is at least 80%.

- [ ] **Step 2: Add the GitHub Actions workflow**

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"
          cache: pip
      - run: python -m pip install --upgrade pip
      - run: python -m pip install -e ".[dev]"
      - run: python -m ruff check .
      - run: python -m mypy src tools
      - run: python -m tools.check_architecture

  test:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest]
        python: ["3.10", "3.13"]
    runs-on: ${{ matrix.os }}
    env:
      QT_QPA_PLATFORM: offscreen
      QSG_RHI_BACKEND: software
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
          cache: pip
      - run: python -m pip install --upgrade pip
      - run: python -m pip install -e ".[dev,ui]"
      - run: python -m pytest -m "not aedt" --cov=inductor_designer --cov-report=xml --cov-report=term-missing
```

- [ ] **Step 3: Link the active plan and CI from the README**

Replace the project status paragraph in `README.md` with:

```markdown
The project is implementing Milestone 0: Foundation and compatibility spike.

- [Active implementation plan](docs/superpowers/plans/2026-07-13-foundation-compatibility-spike.md)
- [Implementation plan index](docs/superpowers/plans/README.md)
```

- [ ] **Step 4: Validate workflow syntax and rerun local gates**

Run: `python -c "import pathlib, yaml; yaml.safe_load(pathlib.Path('.github/workflows/ci.yml').read_text(encoding='utf-8')); print('valid YAML')"`

Expected: `valid YAML`.

Run: `python -m pytest -m "not aedt" --cov=inductor_designer --cov-report=term-missing`

Expected: all tests pass and coverage is at least 80%.

- [ ] **Step 5: Commit**

```powershell
git add .github/workflows/ci.yml README.md
git commit -m "ci: add hosted quality and test matrix"
```

### Task 10: Controlled Commercial and Student compatibility matrix

**Owner:** Human operator with each licensed AEDT edition; an agent may prepare commands and review evidence.

**Files:**
- Create: `compatibility/aedt-matrix.yml`
- Create: `tools/run_aedt_spike.ps1`
- Create: `docs/development/aedt-compatibility-testing.md`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `python -m tools.aedt_spike` from Task 7.
- Produces: one reviewed YAML row per release/edition plus ignored local JSON evidence and `.aedt` artifacts.

- [ ] **Step 1: Add compatibility artifact exclusions**

Append to `.gitignore`:

```gitignore
# Controlled AEDT compatibility artifacts
artifacts/
*.aedt
*.aedt.lock
*.aedtz
```

- [ ] **Step 2: Add the matrix with explicit unverified state**

```yaml
# compatibility/aedt-matrix.yml
schemaVersion: 1
rows:
  - release: "2024.2"
    edition: commercial
    status: unverified
    pyaedtVersion: null
    maxwell2dTrivialProject: null
    maxwell3dTrivialProject: null
    includeDcFields3d: null
    discoveredLimits: []
    evidenceReviewedAt: null
    evidenceReviewedBy: null
  - release: "2024.2"
    edition: student
    status: unverified
    pyaedtVersion: null
    maxwell2dTrivialProject: null
    maxwell3dTrivialProject: null
    includeDcFields3d: null
    discoveredLimits: []
    evidenceReviewedAt: null
    evidenceReviewedBy: null
  - release: "latest-installed"
    edition: commercial
    status: unverified
    pyaedtVersion: null
    maxwell2dTrivialProject: null
    maxwell3dTrivialProject: null
    includeDcFields3d: null
    discoveredLimits: []
    evidenceReviewedAt: null
    evidenceReviewedBy: null
  - release: "latest-installed"
    edition: student
    status: unverified
    pyaedtVersion: null
    maxwell2dTrivialProject: null
    maxwell3dTrivialProject: null
    includeDcFields3d: null
    discoveredLimits: []
    evidenceReviewedAt: null
    evidenceReviewedBy: null
```

- [ ] **Step 3: Add the Windows runner**

```powershell
# tools/run_aedt_spike.ps1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^20[2-9][0-9]\.[12]$')]
    [string]$Release,

    [Parameter(Mandatory = $true)]
    [ValidateSet('commercial', 'student')]
    [string]$Edition,

    [switch]$Graphical
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$runDirectory = Join-Path $root "artifacts/compatibility/$Release-$Edition"
$projectDirectory = Join-Path $runDirectory 'projects'
$evidencePath = Join-Path $runDirectory 'evidence.json'

$arguments = @(
    '-m', 'tools.aedt_spike',
    '--release', $Release,
    '--edition', $Edition,
    '--output-directory', $projectDirectory,
    '--evidence', $evidencePath
)
if ($Graphical) {
    $arguments += '--graphical'
}

Push-Location $root
try {
    & python @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "AEDT compatibility spike failed with exit code $LASTEXITCODE"
    }
    Write-Host "Evidence written to $evidencePath"
}
finally {
    Pop-Location
}
```

- [ ] **Step 4: Document the operator and review checklist**

Create `docs/development/aedt-compatibility-testing.md` with this content:

```markdown
# AEDT Compatibility Testing

## Purpose

This controlled test verifies observed behavior. It does not infer support from an AEDT or PyAEDT version number.

## Prerequisites

- Windows machine with the exact AEDT release and edition under test.
- A valid license for that edition.
- Python 3.10 virtual environment with `python -m pip install -e ".[dev,aedt]"` completed.
- No unrelated AEDT projects open; the runner starts and closes dedicated sessions.

## Run

From the repository root:

```powershell
.\tools\run_aedt_spike.ps1 -Release 2024.2 -Edition commercial -Graphical
```

Repeat with `student`, then with the latest installed Commercial and Student release values. Use graphical mode first because Student gRPC startup behavior must be observed rather than assumed.

## Review evidence

1. Open both generated projects and confirm the named rectangle/box exists.
2. Confirm each project saves, closes, and reopens without a repair warning.
3. Record the exact PyAEDT version from `evidence.json`.
4. In Maxwell 3D, inspect whether the AC Magnetic/Eddy Current setup exposes Include DC Fields; do not set the matrix value from release number alone.
5. Record exact reproducible Student restrictions in `discoveredLimits`; do not include license server names, user names, or machine paths.
6. Update only the matching row in `compatibility/aedt-matrix.yml` to `passed` or `failed`, copy booleans from reviewed evidence, and set ISO-8601 UTC review time and reviewer GitHub handle.
7. Delete local artifacts after the review if they are no longer needed. They must remain ignored by Git.

## Acceptance

Milestone 0 requires reviewed rows for AEDT 2024 R2 Commercial, AEDT 2024 R2 Student, the latest supported Commercial release, and the latest supported Student release. A failed row is valid evidence but blocks a support claim until its cause and policy are documented.
```

- [ ] **Step 5: Verify the runner without launching AEDT**

Run: `powershell -NoProfile -Command '& { $tokens = $null; $parseErrors = $null; [System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path "tools/run_aedt_spike.ps1"), [ref]$tokens, [ref]$parseErrors) > $null; if ($parseErrors.Count) { $parseErrors | Write-Error; exit 1 }; "valid PowerShell" }'`

Expected: `valid PowerShell`.

Run: `python -c "import pathlib, yaml; data=yaml.safe_load(pathlib.Path('compatibility/aedt-matrix.yml').read_text()); assert len(data['rows']) == 4; print('4 matrix rows')"`

Expected: `4 matrix rows`.

- [ ] **Step 6: Run and review each controlled matrix row**

Run the command below with the exact installed release for each of the four edition/release combinations:

```powershell
.\tools\run_aedt_spike.ps1 -Release 2024.2 -Edition commercial -Graphical
.\tools\run_aedt_spike.ps1 -Release 2024.2 -Edition student -Graphical
.\tools\run_aedt_spike.ps1 -Release 2026.2 -Edition commercial -Graphical
.\tools\run_aedt_spike.ps1 -Release 2026.2 -Edition student -Graphical
```

Expected for each run: exit code 0, `evidence.json` reports both artifacts as created and saved, and manual reopen succeeds. If the latest installed release is not `2026.2`, replace only that argument with the exact installed `YYYY.R` value and update the matrix row from `latest-installed` to that value.

- [ ] **Step 7: Commit reviewed matrix evidence metadata, not generated artifacts**

```powershell
git add .gitignore compatibility/aedt-matrix.yml tools/run_aedt_spike.ps1 docs/development/aedt-compatibility-testing.md
git commit -m "docs: record controlled AEDT compatibility matrix"
```

### Task 11: Milestone verification and handoff

**Owner:** The agent closing Milestone 0, after a human operator completes Task 10.

**Files:**
- Modify: `docs/development/ROADMAP.md`
- Modify: `docs/superpowers/plans/README.md`

**Interfaces:**
- Consumes: All Task 1-10 deliverables and reviewed matrix rows.
- Produces: Accepted Milestone 0 interface inventory and an explicit authorization point for the Milestone 1 plan.

- [ ] **Step 1: Run every non-AEDT release gate from a clean environment**

Run:

```powershell
python -m pip install -e ".[dev,ui]"
python -m ruff check .
python -m mypy src tools
python -m tools.check_architecture
python -m pytest -m "not aedt" --cov=inductor_designer --cov-report=term-missing
```

Expected: installation succeeds; Ruff and mypy report no issues; boundary checker exits 0; all tests pass; coverage is at least 80%.

- [ ] **Step 2: Verify repository hygiene**

Run: `git status --short`

Expected: only the intended roadmap and plan-index closeout edits are listed; no `.aedt`, evidence JSON, solver outputs, credentials, or unrelated files appear.

Run: `git check-ignore artifacts/compatibility/example/evidence.json example.aedt`

Expected: both paths are printed, proving they are ignored.

- [ ] **Step 3: Record the accepted interfaces and evidence locations in the roadmap**

Append this section under Milestone 0 in `docs/development/ROADMAP.md` only after CI passes and every required compatibility row has a reviewed `passed` or `failed` status:

```markdown
### Milestone 0 verification record

- Automated evidence: `.github/workflows/ci.yml` on Python 3.10 and 3.13 for Windows and Linux.
- Controlled AEDT evidence: `compatibility/aedt-matrix.yml` for AEDT 2024 R2 and the latest reviewed release in Commercial and Student editions.
- Accepted interfaces: `AedtGateway`, `AedtProbeRequest`, `AedtProbeResult`, `CapabilitySnapshot`, `select_dc_bias_strategy`, `SchemaRepository`.
- Generated AEDT artifacts: excluded from Git and reproducible with `tools/run_aedt_spike.ps1`.
- Compatibility rule: only reviewed matrix values may enable native or fallback behavior.
```

- [ ] **Step 4: Mark Milestone 0 complete in the plan index**

Change the Milestone 0 entry condition cell in `docs/superpowers/plans/README.md` from `Approved product design` to `Completed; see the Milestone 0 verification record in docs/development/ROADMAP.md`.

- [ ] **Step 5: Rerun documentation checks**

Run: `rg -n "T[B]D|T[O]DO|implement[ ]later|fill[ ]in" docs/development/ROADMAP.md docs/superpowers/plans/README.md`

Expected: no output.

Run: `git diff --check`

Expected: no output.

- [ ] **Step 6: Commit the milestone closeout**

```powershell
git add docs/development/ROADMAP.md docs/superpowers/plans/README.md
git commit -m "docs: close foundation compatibility milestone"
```

- [ ] **Step 7: Handoff before planning Milestone 1**

The handoff message must state the exact commit hash, changed public interfaces, automated test counts, coverage, all four reviewed AEDT rows, observed Student restrictions, and any failed matrix row. The next planning session must read that evidence before writing the Toroid Domain and Catalogs implementation plan.

## Milestone 0 acceptance criteria

- The editable package installs on Python 3.10 and 3.13 with at least 80% branch-aware coverage in Milestone 0.
- Hosted Windows and Linux CI passes without importing or launching AEDT.
- Architecture tests prevent PyAEDT, Qt, SQLite, and OS imports from inner packages.
- The version 1 project envelope validates a stable fixture and rejects invalid/unknown versions.
- Capability policy selects native 3D DC fields only from observed capability evidence, uses the documented 2024 R2 approximation, and blocks unsupported 2D behavior.
- The recording gateway and injected PyAEDT adapter pass the same contract without AEDT.
- The real spike creates, saves, closes, and reopens trivial Maxwell 2D and 3D projects.
- The Qt Quick 3D Guided Studio shell loads in an offscreen smoke test.
- Commercial and Student results are reviewed for AEDT 2024 R2 and the latest installed release.
- Generated AEDT projects and raw local evidence remain outside Git.

## Authoritative implementation references

- [PyAEDT installation and Student support](https://aedt.docs.pyansys.com/version/stable/Getting_started/Installation.html)
- [PyAEDT versions and interfaces](https://aedt.docs.pyansys.com/version/stable/Getting_started/versioning.html)
- [PyAEDT basic session lifecycle](https://aedt.docs.pyansys.com/version/stable/User_guide/intro.html)
- [PyAEDT Maxwell 3D constructor](https://aedt.docs.pyansys.com/version/stable/API/_autosummary/ansys.aedt.core.maxwell.Maxwell3d.html)
- [PyAEDT command-line session and test configuration](https://aedt.docs.pyansys.com/version/stable/Getting_started/cli.html)
