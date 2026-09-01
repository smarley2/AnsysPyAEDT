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

from inductor_designer.application.services.aedt_support import (
    SUPPORTED_AEDT_EDITION,
    SUPPORTED_AEDT_RELEASE,
)
from inductor_designer.application.services.dc_bias_visibility import (
    DcBiasVisibility,
    dc_bias_visibility,
)
from inductor_designer.application.services.solver_visibility import (
    visible_window_support,
)
from inductor_designer.domain.project import MeshIntent, RequestedOutput, SimulationRecipe
from inductor_designer.simulation.run_contracts import RunBackend, RunMode
from inductor_designer.ui.generation_lines import GenerationBackend, run_backend_for

if TYPE_CHECKING:
    from inductor_designer.adapters.system.installations import (
        AedtInstallation,
        UnsupportedAedtInstallation,
    )
    from inductor_designer.simulation.capabilities import CapabilitySnapshot
    from inductor_designer.ui.generation_controller import GenerationController
    from inductor_designer.ui.project_session import ProjectSession

_MODE_NOTES = {
    RunMode.GENERATE_ONLY: (
        "Generate Only writes the solver project and stops; open it in the "
        "solver to run it yourself."
    ),
    RunMode.GENERATE_AND_SOLVE: (
        "Generate and Solve runs the solve and reports its stages. Normalized "
        "results arrive with M8b and M8c; this run writes the solver's own "
        "output plus a stage log."
    ),
}


class SimulationController(QObject):
    configurationChanged = Signal()
    visibilityChanged = Signal()
    gateChanged = Signal()

    def __init__(
        self,
        session: ProjectSession,
        generation: GenerationController,
        capabilities: CapabilitySnapshot,
        aedt_installation: AedtInstallation | None = None,
        unsupported_aedt_installation: UnsupportedAedtInstallation | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._generation = generation
        self._capabilities = capabilities
        # What M10's `installations.detect_aedt()` / `detect_unsupported_aedt()`
        # found on this machine at startup (Task 2) -- carried here, not
        # re-detected, so the Simulation screen never starts a desktop of its
        # own just to draw a label. `None`/`None` reads as "AEDT absent",
        # which is the safe default for a caller that has not wired this in.
        self._aedt_installation = aedt_installation
        self._unsupported_aedt_installation = unsupported_aedt_installation
        self._backend = GenerationBackend.MAXWELL_3D
        self._mode = RunMode.GENERATE_ONLY
        self._show_solver_window = False
        # Set when generate() refuses because DC bias would be ignored, so
        # proceedAcOnly() can verify the confirmation the caller obtained
        # still matches the current backend (finding: the invariant must
        # live here, not in the QML wiring that happens to call it once).
        self._pending_ac_only_backend: GenerationBackend | None = None
        session.dirtyChanged.connect(self.gateChanged)
        # `documentPath` changes on Open/Save As without necessarily also
        # changing `dirty` (a freshly opened project is clean both before and
        # after), so the gate needs its own hook on that signal too.
        session.documentPathChanged.connect(self.gateChanged)
        generation.busyChanged.connect(self.gateChanged)
        # The DC-bias notice depends on the operating point (edited from the
        # Windings screen, not from here), so it needs its own hook too.
        session.projectChanged.connect(self.configurationChanged)

    def _get_backend_options(self) -> list[str]:
        return [item.value for item in GenerationBackend]

    backendOptions = Property(list, _get_backend_options, constant=True)

    def _get_backend(self) -> str:
        return self._backend.value

    backend = Property(str, _get_backend, notify=configurationChanged)

    def _get_aedt_status_notice(self) -> str:
        """Empty when there is nothing to warn about: FEMM needs no AEDT at
        all, and the supported release being present is the unremarkable
        case. Otherwise names exactly what is wrong -- absent, or present but
        the wrong release -- so a mismatch is visible before Generate is
        clicked, not after a run fails against it."""
        if run_backend_for(self._backend) is RunBackend.FEMM:
            return ""
        if self._aedt_installation is not None:
            return ""
        wanted = f"AEDT {SUPPORTED_AEDT_RELEASE} {SUPPORTED_AEDT_EDITION.value}"
        if self._unsupported_aedt_installation is not None:
            found = self._unsupported_aedt_installation
            return (
                f"AEDT {found.release} is installed, but this application "
                f"supports {wanted} only. Install it to generate with this backend."
            )
        return (
            f"{wanted} was not found on this machine. "
            "Install it to generate with this backend."
        )

    aedtStatusNotice = Property(str, _get_aedt_status_notice, notify=configurationChanged)

    def _get_mode_options(self) -> list[str]:
        return [item.value for item in RunMode]

    modeOptions = Property(list, _get_mode_options, constant=True)

    def _get_mode(self) -> str:
        return self._mode.value

    mode = Property(str, _get_mode, notify=configurationChanged)

    def _get_mode_label(self) -> str:
        return self._mode.value

    modeLabel = Property(str, _get_mode_label, notify=configurationChanged)

    def _get_mode_note(self) -> str:
        return _MODE_NOTES[self._mode]

    modeNote = Property(str, _get_mode_note, notify=configurationChanged)

    @Slot(str, result=bool)
    def setMode(self, mode_label: str) -> bool:  # noqa: N802 - Qt slot naming
        try:
            mode = RunMode(mode_label)
        except ValueError:
            self._session.set_status(f"Unknown run mode: {mode_label}")
            return False
        if mode is not self._mode:
            self._mode = mode
            self.configurationChanged.emit()
        return True

    @Slot(result=bool)
    def cancel(self) -> bool:
        """Ask the running backend to stop at its next stage boundary."""
        return self._generation.cancel()

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

    def _dc_bias(self) -> DcBiasVisibility:
        dc_requested = any(
            winding.dc_current_a != 0.0
            for winding in self._session.project.operating_point.windings
        )
        return dc_bias_visibility(
            run_backend_for(self._backend),
            self._capabilities,
            dc_requested=dc_requested,
        )

    def _get_dc_bias_ignored(self) -> bool:
        return self._dc_bias().ignored

    dcBiasIgnored = Property(bool, _get_dc_bias_ignored, notify=configurationChanged)

    def _get_dc_bias_notice(self) -> str:
        return self._dc_bias().notice

    dcBiasNotice = Property(str, _get_dc_bias_notice, notify=configurationChanged)

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

    def _start(self, *, dc_confirmed: bool) -> bool:
        blocked = self._gate()
        if blocked:
            self._session.set_status(blocked)
            return False
        if self._dc_bias().ignored and not dc_confirmed:
            # QML must show the AC-only confirmation dialog instead of
            # retrying silently; this refusal never starts a run. Record
            # which backend the caller is about to be asked to confirm, so
            # a later proceedAcOnly() can check it is still the same one.
            self._pending_ac_only_backend = self._backend
            return False
        # Either this run needed no confirmation, or it is about to consume
        # one -- either way, nothing should stay pending afterwards.
        self._pending_ac_only_backend = None
        self._generation.generate(
            self._backend.value,
            self._show_solver_window,
            self._mode is RunMode.GENERATE_AND_SOLVE,
        )
        return True

    @Slot(result=bool)
    def generate(self) -> bool:
        return self._start(dc_confirmed=False)

    @Slot(result=bool)
    def proceedAcOnly(self) -> bool:
        """Start the run after the user confirmed the AC-only DC-bias notice.

        Only authorises a run for the exact backend a refused `generate()`
        warned about. There is no other source of "confirmed" for this
        controller, so a call with no matching pending refusal -- none ever
        happened, the backend changed since, or a previous confirmation
        already consumed it -- refuses instead of silently starting an
        unconfirmed AC-only run.
        """
        if self._pending_ac_only_backend != self._backend:
            stale = self._pending_ac_only_backend is not None
            self._pending_ac_only_backend = None
            self._session.set_status(
                "The backend changed since the DC-bias confirmation; confirm "
                "again before starting."
                if stale
                else "No DC-bias confirmation is pending for the current backend."
            )
            return False
        return self._start(dc_confirmed=True)
