from __future__ import annotations

import os
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.application.services.aedt_support import (  # noqa: E402
    SUPPORTED_AEDT_EDITION,
    SUPPORTED_AEDT_RELEASE,
)
from inductor_designer.application.services.maxwell_export import (  # noqa: E402
    RunGenerationFailed,
    generate_run,
)
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease  # noqa: E402
from inductor_designer.simulation.run_contracts import (  # noqa: E402
    RunBackend,
    RunMode,
    RunRequest,
)
from inductor_designer.ui.generation_controller import (  # noqa: E402
    CurrentProjectProvider,
    GenerationController,
)
from inductor_designer.ui.main import (  # noqa: E402
    _build_generation_controller,
    _persist_and_publish_project,
)
from tests.fakes.femm_solver import RecordingFemmSolver  # noqa: E402
from tests.fakes.maxwell2d_exporter import RecordingMaxwell2dExporter  # noqa: E402
from tests.fakes.maxwell_exporter import RecordingMaxwell3dExporter  # noqa: E402
from tests.unit.application.test_maxwell_export import (  # noqa: E402
    CAPABILITIES,
    CATALOG,
    project_for_runs,
)
from tests.unit.domain.test_project import make_project  # noqa: E402

pytestmark = pytest.mark.ui


# ponytail: QGuiApplication, not QCoreApplication - this file shares a process
# with test_qml_smoke.py/test_preview_smoke.py under `pytest -m ui`, and once
# one test creates the base QCoreApplication the others' QGuiApplication([])
# call crashes (native Qt singleton mismatch). Same app class everywhere
# sidesteps the ordering hazard.
def _wait_until_idle(app: QGuiApplication, controller: GenerationController) -> None:
    deadline = time.monotonic() + 5.0
    while controller.busy:
        if time.monotonic() > deadline:
            raise TimeoutError("generation controller stayed busy")
        app.processEvents()
        time.sleep(0.01)


def test_generate_runs_stub_runner_and_reports_lines() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    controller = GenerationController(lambda backend_label: ("a", "b"))

    assert controller.lines == []
    assert controller.busy is False

    controller.generate("Maxwell 3D")
    _wait_until_idle(app, controller)

    assert controller.lines == ["a", "b"]
    assert controller.busy is False


def test_generate_ignores_calls_while_busy() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    calls: list[str] = []
    release = threading.Event()

    def runner(backend_label: str) -> tuple[str, ...]:
        calls.append(backend_label)
        release.wait(timeout=5.0)
        return ("done",)

    controller = GenerationController(runner)
    controller.generate("Maxwell 3D")
    controller.generate("FEMM 2D")  # ignored: busy
    release.set()
    _wait_until_idle(app, controller)

    assert calls == ["Maxwell 3D"]
    assert controller.lines == ["done"]


def test_generate_handles_runner_exception() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])

    def failing_runner(backend_label: str) -> tuple[str, ...]:
        raise ValueError("test error from runner")

    controller = GenerationController(failing_runner)
    controller.generate("Maxwell 3D")
    _wait_until_idle(app, controller)

    assert controller.busy is False
    assert len(controller.lines) == 1
    assert "Generation failed:" in controller.lines[0]
    assert "test error from runner" in controller.lines[0]


def test_generate_retains_failed_manifest_from_runner_result(tmp_path: Path) -> None:
    app = QGuiApplication.instance() or QGuiApplication([])

    class _RaisingMaxwell3dExporter(RecordingMaxwell3dExporter):
        def export(self, request: object) -> object:  # type: ignore[override]
            raise RuntimeError("UI adapter failed")

    with pytest.raises(RunGenerationFailed) as raised:
        generate_run(
            project_for_runs(),
            RunRequest(RunBackend.MAXWELL_3D, RunMode.GENERATE_ONLY),
            CATALOG,
            CAPABILITIES,
            tmp_path,
            maxwell3d_exporter=_RaisingMaxwell3dExporter(),
            maxwell2d_exporter=RecordingMaxwell2dExporter(),
            femm_solver=RecordingFemmSolver(),
            run_id="ui-failed-run",
            application_version="ui-test",
        )
    failed_manifest = raised.value.manifest

    class _FailedResult:
        def __init__(self) -> None:
            self.lines = ("Generation failed: UI adapter failed",)
            self.failed_manifest = failed_manifest

        def __iter__(self) -> object:
            return iter(self.lines)

    controller = GenerationController(lambda _backend: _FailedResult())  # type: ignore[arg-type]
    controller.generate("Maxwell 3D")
    _wait_until_idle(app, controller)

    assert controller.lines == ["Generation failed: UI adapter failed"]
    assert controller.failed_manifest is failed_manifest


def test_project_provider_publishes_only_after_persistence_succeeds() -> None:
    original = make_project()
    updated = replace(original, name="updated")
    provider = CurrentProjectProvider(original)

    def failing_save(_project: object) -> None:
        raise OSError("disk save failed")

    with pytest.raises(OSError, match="disk save failed"):
        _persist_and_publish_project(updated, failing_save, provider)
    assert provider.current() is original

    saved: list[object] = []
    _persist_and_publish_project(updated, saved.append, provider)
    assert saved == [updated]
    assert provider.current() is updated


def test_generation_uses_current_project_and_fixed_supported_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from inductor_designer.adapters.catalog import sqlite_repository
    from inductor_designer.adapters.compatibility import matrix_repository
    from inductor_designer.adapters.femm import solver as femm_solver
    from inductor_designer.adapters.pyaedt import maxwell2d, maxwell3d
    from inductor_designer.ui import generation_lines

    original = make_project()
    updated = replace(original, name="provider changed project")
    provider = CurrentProjectProvider(original)
    capability_calls: list[tuple[AedtRelease, AedtEdition]] = []
    generation_calls: list[tuple[object, object]] = []

    class Matrix:
        def snapshot_for(
            self,
            release: AedtRelease,
            edition: AedtEdition,
        ) -> object:
            capability_calls.append((release, edition))
            return object()

    monkeypatch.setattr(sqlite_repository, "SqliteCatalogRepository", lambda _path: object())
    monkeypatch.setattr(matrix_repository, "MatrixCapabilityRepository", lambda _path: Matrix())
    monkeypatch.setattr(maxwell3d, "PyaedtMaxwell3dExporter", lambda: object())
    monkeypatch.setattr(maxwell2d, "PyaedtMaxwell2dExporter", lambda: object())
    monkeypatch.setattr(femm_solver, "PyfemmSolver", lambda: object())

    def record_generation(
        _backend: object,
        project: object,
        _catalog: object,
        _capabilities: object,
        output_directory: object,
        **_adapters: object,
    ) -> tuple[str, ...]:
        generation_calls.append((project, output_directory))
        return ("done",)

    monkeypatch.setattr(generation_lines, "run_generation", record_generation)
    controller = _build_generation_controller(provider, object(), object())  # type: ignore[arg-type]
    provider.replace(updated)
    app = QGuiApplication.instance() or QGuiApplication([])

    controller.generate("Maxwell 3D")
    _wait_until_idle(app, controller)

    assert capability_calls == [(SUPPORTED_AEDT_RELEASE, SUPPORTED_AEDT_EDITION)]
    assert generation_calls[0][0] is updated
    assert generation_calls[0][1] == (
        Path("artifacts") / "studio" / "provider_changed_project"
    )
