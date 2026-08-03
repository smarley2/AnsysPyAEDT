"""The Simulation screen (specification section 4.4, ADR 0007).

Backend, mesh intent, convergence intent, and requested outputs live in the
Project document, so every edit here goes through the session. Frequency and
temperature are deliberately absent: they are shared operating-point inputs
owned by the Windings screen.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import TYPE_CHECKING

from PySide6.QtCore import Property, QObject, Signal, Slot

from inductor_designer.application.services.solver_visibility import (
    visible_window_support,
)
from inductor_designer.domain.project import MeshIntent, RequestedOutput, SimulationRecipe
from inductor_designer.simulation.run_contracts import RunMode
from inductor_designer.ui.generation_lines import GenerationBackend, run_backend_for

if TYPE_CHECKING:
    from inductor_designer.simulation.capabilities import CapabilitySnapshot
    from inductor_designer.ui.generation_controller import GenerationController
    from inductor_designer.ui.project_session import ProjectSession

_MODE_NOTE = (
    "Guided Studio generates the solver project without solving it. Generate "
    "and Solve arrives with the M8 result artifacts."
)


class SimulationController(QObject):
    configurationChanged = Signal()
    visibilityChanged = Signal()
    gateChanged = Signal()

    def __init__(
        self,
        session: ProjectSession,
        generation: GenerationController,
        capabilities: CapabilitySnapshot,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._generation = generation
        self._capabilities = capabilities
        self._backend = GenerationBackend.MAXWELL_3D
        self._show_solver_window = False
        session.dirtyChanged.connect(self.gateChanged)
        generation.busyChanged.connect(self.gateChanged)

    def _get_backend_options(self) -> list[str]:
        return [item.value for item in GenerationBackend]

    backendOptions = Property(list, _get_backend_options, constant=True)

    def _get_backend(self) -> str:
        return self._backend.value

    backend = Property(str, _get_backend, notify=configurationChanged)

    def _get_mode_label(self) -> str:
        return RunMode.GENERATE_ONLY.value

    modeLabel = Property(str, _get_mode_label, constant=True)

    def _get_mode_note(self) -> str:
        return _MODE_NOTE

    modeNote = Property(str, _get_mode_note, constant=True)

    def _get_mesh_intent_options(self) -> list[str]:
        return [item.value for item in MeshIntent]

    meshIntentOptions = Property(list, _get_mesh_intent_options, constant=True)

    def _get_mesh_intent(self) -> str:
        return self._session.project.simulation_recipe.mesh_intent.value

    meshIntent = Property(str, _get_mesh_intent, notify=configurationChanged)

    def _get_maximum_passes(self) -> int:
        return self._session.project.simulation_recipe.maximum_passes

    maximumPasses = Property(int, _get_maximum_passes, notify=configurationChanged)

    def _get_percent_error(self) -> float:
        return self._session.project.simulation_recipe.percent_error

    percentError = Property(float, _get_percent_error, notify=configurationChanged)

    def _get_requested_outputs(self) -> list[dict[str, object]]:
        selected = set(self._session.project.simulation_recipe.requested_outputs)
        return [
            {
                "value": item.value,
                "label": item.value.replace("-", " "),
                "selected": item in selected,
            }
            for item in RequestedOutput
        ]

    requestedOutputs = Property(list, _get_requested_outputs, notify=configurationChanged)

    def _get_show_solver_window(self) -> bool:
        return self._show_solver_window

    showSolverWindow = Property(bool, _get_show_solver_window, notify=visibilityChanged)

    def _support(self) -> tuple[bool, str]:
        support = visible_window_support(
            run_backend_for(self._backend), self._capabilities
        )
        return support.supported, support.reason or ""

    def _get_visible_window_supported(self) -> bool:
        return self._support()[0]

    visibleWindowSupported = Property(
        bool, _get_visible_window_supported, notify=visibilityChanged
    )

    def _get_visible_window_reason(self) -> str:
        return self._support()[1]

    visibleWindowReason = Property(
        str, _get_visible_window_reason, notify=visibilityChanged
    )

    def _gate(self) -> str:
        """Why a run cannot start, or an empty string when it can."""
        if self._generation.busy:
            return "A generation run is already in progress."
        if not self._session.documentPath:
            return (
                "The project has no document path. Save the project to a file "
                "before running."
            )
        if self._session.dirty:
            return (
                "The project has unsaved edits. Save the project before running "
                "so the run matches what is on disk."
            )
        return ""

    def _get_can_generate(self) -> bool:
        return self._gate() == ""

    canGenerate = Property(bool, _get_can_generate, notify=gateChanged)

    def _get_blocked_reason(self) -> str:
        return self._gate()

    blockedReason = Property(str, _get_blocked_reason, notify=gateChanged)

    def _apply_recipe(self, recipe: SimulationRecipe) -> None:
        self._session.apply(replace(self._session.project, simulation_recipe=recipe))
        self.configurationChanged.emit()

    @Slot(str, result=bool)
    def setBackend(self, backend_label: str) -> bool:
        try:
            backend = GenerationBackend(backend_label)
        except ValueError:
            self._session.set_status(f"Unknown backend: {backend_label}")
            return False
        self._backend = backend
        if not self._support()[0]:
            self._show_solver_window = False
        self.configurationChanged.emit()
        self.visibilityChanged.emit()
        return True

    @Slot(str, result=bool)
    def setMeshIntent(self, mesh_intent: str) -> bool:
        try:
            intent = MeshIntent(mesh_intent)
        except ValueError:
            self._session.set_status(f"Unknown mesh intent: {mesh_intent}")
            return False
        self._apply_recipe(
            replace(self._session.project.simulation_recipe, mesh_intent=intent)
        )
        return True

    @Slot(str, result=bool)
    def setMaximumPasses(self, value: str) -> bool:
        try:
            number = int(value.strip())
            recipe = replace(
                self._session.project.simulation_recipe, maximum_passes=number
            )
        except ValueError as error:
            # SimulationRecipe refuses a nonpositive count; report, never crash.
            self._session.set_status(f"Unable to apply maximum passes: {error}")
            return False
        self._apply_recipe(recipe)
        return True

    @Slot(str, result=bool)
    def setPercentError(self, value: str) -> bool:
        try:
            number = float(value.strip().replace(",", "."))
            if not math.isfinite(number):
                raise ValueError("Percent error must be finite")
            recipe = replace(
                self._session.project.simulation_recipe, percent_error=number
            )
        except ValueError as error:
            self._session.set_status(f"Unable to apply percent error: {error}")
            return False
        self._apply_recipe(recipe)
        return True

    @Slot(str, bool, result=bool)
    def toggleRequestedOutput(self, value: str, selected: bool) -> bool:
        try:
            output = RequestedOutput(value)
        except ValueError:
            self._session.set_status(f"Unknown requested output: {value}")
            return False
        current = list(self._session.project.simulation_recipe.requested_outputs)
        if selected and output not in current:
            current.append(output)
        elif not selected and output in current:
            current.remove(output)
        self._apply_recipe(
            replace(
                self._session.project.simulation_recipe,
                requested_outputs=tuple(current),
            )
        )
        return True

    @Slot(bool, result=bool)
    def setShowSolverWindow(self, show: bool) -> bool:
        """An unsupported visible mode is refused with its reason, never ignored."""
        if show and not self._support()[0]:
            self._session.set_status(
                f"Show solver window is unavailable: {self._support()[1]}"
            )
            return False
        self._show_solver_window = show
        self.visibilityChanged.emit()
        return True

    @Slot(result=bool)
    def generate(self) -> bool:
        blocked = self._gate()
        if blocked:
            self._session.set_status(blocked)
            return False
        self._generation.generate(self._backend.value, self._show_solver_window)
        return True
