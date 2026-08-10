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


class WatchableApp(Protocol):
    are_there_simulations_running: object

    def analyze_setup(self, name: str, *, blocking: bool = True) -> bool: ...

    def stop_simulations(self, clean_stop: bool = True) -> object: ...


def analyze_watched(
    app: WatchableApp,
    setup_name: str,
    *,
    cancellation: CancellationToken | None = None,
) -> None:
    """Solve `setup_name`, returning once the desktop reports no solver running.

    Raises `RunCancelled` after stopping the solver when the run is cancelled,
    and `RuntimeError` when the solve refuses to start.
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
