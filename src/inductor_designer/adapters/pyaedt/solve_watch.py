"""Wait for a Maxwell solve without parking the process inside AEDT.

`analyze_setup(name)` defaults to a blocking call: one Python call that returns
only when the solve is over. The AEDT desktop plugin keeps the interpreter
lock for that whole call, so no other Python code runs in the process, and the
Qt user interface stops repainting even though the run owns a worker thread.

Starting the solve non-blocking and waiting in Python instead gives the lock
back on every `time.sleep`, and makes cancellation reach the solver itself
rather than only the next stage boundary.
"""

from __future__ import annotations

import time
from typing import Protocol

from inductor_designer.simulation.run_control import (
    CancellationToken,
    RunCancelled,
    is_cancelled,
)

_POLL_SECONDS = 2.0
# The desktop needs a moment to register a freshly started solve, so an idle
# report right after the start means "not yet", not "already finished".
# ponytail: a fixed number of idle polls, not a solver handshake; raise it if
# a machine is ever seen taking longer than this to register a solve.
_IDLE_POLLS_TO_FINISH = 5


# AEDT's own verdict on a finished solve, from the setup profile. Anything
# else -- "Engine Detected Error" is the one seen live -- means the solver
# stopped early.
NORMAL_COMPLETION = "Normal Completion"


class WatchableApp(Protocol):
    are_there_simulations_running: object

    def analyze_setup(self, name: str, *, blocking: bool = True) -> bool: ...

    def stop_simulations(self, clean_stop: bool = True) -> object: ...

    def solve_status(self, name: str) -> str: ...


def analyze_watched(
    app: WatchableApp,
    setup_name: str,
    *,
    cancellation: CancellationToken | None = None,
) -> None:
    """Solve `setup_name`, returning once AEDT reports the solve completed.

    Raises `RunCancelled` after stopping the solver when the run is cancelled,
    and `RuntimeError` when the solve refuses to start or ends badly.

    "No solver running" is not the same as "solved": a solver that dies mid-way
    also stops running. On 2026-08-18 a live Maxwell 3D run lost its eddy-current
    child process after the first adaptive pass ("Unable to create child
    process: 3dedy", then "Simulation completed with execution error"). The poll
    loop saw an idle desktop and the run was recorded `succeeded`, publishing
    the losses that pass had produced while every matrix entry read NaN. AEDT's
    profile said `Engine Detected Error` the whole time, so that verdict is now
    what ends the wait.
    """
    if not app.analyze_setup(setup_name, blocking=False):
        raise RuntimeError(f"Setup {setup_name} did not start solving.")
    idle_polls = 0
    while idle_polls < _IDLE_POLLS_TO_FINISH:
        time.sleep(_POLL_SECONDS)
        if is_cancelled(cancellation):
            app.stop_simulations(clean_stop=True)
            raise RunCancelled("analyze")
        idle_polls = 0 if app.are_there_simulations_running else idle_polls + 1
    status = app.solve_status(setup_name)
    # An empty status is "AEDT did not say", not "AEDT said it failed": older
    # profiles and the geometry-only path expose none, and refusing those would
    # fail runs that are fine. A wrong number still cannot slip through, because
    # an incomplete solve leaves its quantities unavailable with a reason.
    if status and status != NORMAL_COMPLETION:
        raise RuntimeError(
            f"Setup {setup_name} stopped early: AEDT reported {status!r} "
            f"instead of {NORMAL_COMPLETION!r}."
        )
