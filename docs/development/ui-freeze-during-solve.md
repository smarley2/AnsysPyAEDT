# Bug: the application window stops responding while Maxwell 3D solves

- Reported by: Fabio Posser, 2026-08-10
- Status: fix implemented on `claude/m8b-scalar-results`; root cause still to be
  confirmed on the live workstation, and the fix still needs live evidence
- Affects: `Generate and Solve` runs, Maxwell 3D and Maxwell 2D
- Severity: high for usability, no data loss (the run itself completes)

## Symptom

Starting a `Generate and Solve` run from the Simulation screen makes the
application window turn into a Windows "Not Responding" ghost window for the
whole duration of the solve. The window does not repaint, the stage log stops
updating, and `Cancel` cannot be clicked. When the solve finishes, the window
recovers on its own and the remaining stages are reported normally, so the run
result is correct: only the user interface is dead while it lasts.

## What is already ruled out

The run does not execute on the Qt main thread. `GenerationController.generate`
starts a `threading.Thread` and every exporter call happens there
([generation_controller.py:196](../../src/inductor_designer/ui/generation_controller.py:196)).
Stage events cross back through Qt signals, which are queued for the main
thread. So "move the solve off the UI thread" is not the fix; it is already
off it.

## Where the process actually blocks

`Generate and Solve` reaches one blocking call and stays there:

- [maxwell3d.py:404](../../src/inductor_designer/adapters/pyaedt/maxwell3d.py:404)
  `_stage_analyze` calls `app.analyze_setup(plan.setup.name)`
- [maxwell2d.py:271](../../src/inductor_designer/adapters/pyaedt/maxwell2d.py:271)
  is the same code for 2D

PyAEDT 1.2.0 forwards that to a single blocking call into the AEDT desktop
plugin, `self.odesign.Analyze(name, blocking)` with `blocking=True`
(`ansys.aedt.core.application.analysis.Analysis.analyze_setup`). One Python
call that returns only when the solve is over: minutes to hours.

## Root-cause hypotheses, most likely first

1. **The AEDT desktop plugin holds the GIL for the whole `Analyze` call.**
   The PyAEDT gRPC/COM plugin is a native extension shipped by Ansys. If it
   does not release the GIL around the blocking call, no other Python code in
   the process can run, including the QML property getters and signal handlers
   the Qt render loop calls into. The window then stops repainting even though
   the C++ event loop is alive, which is exactly what Windows labels
   "Not Responding". This hypothesis explains the symptom completely and is
   consistent with the run being on a worker thread.
2. **Solver CPU starvation.** Maxwell takes every core by default. The UI
   thread would stutter, but a full multi-minute freeze with no repaint at all
   is not what oversubscription normally looks like. Secondary.
3. **COM apartment marshalling.** If the session is a COM (non-gRPC) session,
   calls made from a `threading.Thread` can marshal back through the main
   thread's STA, which would tie the main thread to the solve. Only applies
   when gRPC is disabled; AEDT 2025.2 uses gRPC by default. Least likely.

## Experiment that discriminates them

Run on the workstation with AEDT installed. A main-thread heartbeat prints
while a worker thread performs a slow AEDT call. If the heartbeat stops, the
GIL is held (hypothesis 1). If it keeps printing but late and irregular, it is
scheduling pressure (hypothesis 2).

```bash
.venv/Scripts/python.exe tools/aedt_gil_probe.py
```

```python
# tools/aedt_gil_probe.py  (not committed yet; part of the proposed fix)
import threading, time
from ansys.aedt.core import Maxwell3d

def solve(app, name):
    app.analyze_setup(name)

app = Maxwell3d(version="2025.2", non_graphical=False, new_desktop=True)
# ... open a small solved-in-a-minute setup named "Setup1" ...
threading.Thread(target=solve, args=(app, "Setup1"), daemon=True).start()
start = time.monotonic()
while threading.active_count() > 1:
    print(f"heartbeat {time.monotonic() - start:.1f}s", flush=True)
    time.sleep(0.5)
```

Record the observed gap between heartbeats in this file before implementing.

## The fix, as implemented

Stop making one long blocking call. Start the solve non-blocking, then wait in
Python with a sleep between polls. `time.sleep` releases the GIL
unconditionally, so the rest of the process gets it back regardless of which of
the three hypotheses is true.

All APIs used exist in the pinned PyAEDT (verified against the installed
1.2.0): `analyze_setup(..., blocking=False)`,
`are_there_simulations_running`, `stop_simulations(clean_stop)`.

One helper, [solve_watch.py](../../src/inductor_designer/adapters/pyaedt/solve_watch.py),
shared by both adapters because `_stage_analyze` was already identical in 2D
and 3D: start with `blocking=False`, then poll `are_there_simulations_running`
every 2 s until the desktop reports idle five polls in a row. The five idle
polls cover the moment between the start call returning and the solver
registering itself; a single idle report right after the start would otherwise
end the stage before the solve began.

Cancellation is checked on every poll. A cancelled run calls
`stop_simulations(clean_stop=True)` and raises `RunCancelled`, which both
exporters turn into a `cancelled` run rather than a failed one, and no result
extraction runs on a solve that was stopped halfway.

The `Maxwell3dApp` / `Maxwell2dApp` protocols grew `analyze_setup(name, *,
blocking)`, `are_there_simulations_running` and `stop_simulations`, so the test
fakes stay in control of what the watch observes.

### Limitation this also removes

Cancellation is now real during `analyze` instead of only at a stage boundary,
which retires the known limitation recorded in
[m8a-live-solve-evidence.md](m8a-live-solve-evidence.md#known-limitations).

### Deliberately left out

A live progress line during the solve. It needs a second cadence knob and would
add one panel line every poll for the length of the solve; the stage log still
shows `analyze: started` and then the solved message.

### Deliberately not proposed

- **Running the solve in a separate process.** It would isolate the GIL
  completely, but it means serializing the plan, a second AEDT session model,
  and a new failure surface for a problem a poll loop already solves.
- **`solve_in_batch=True` / `submit_job`.** Same reasoning: a batch solve
  changes where results land and how the desktop session is reused.
- **Capping solver cores.** Only relevant if the experiment points at
  hypothesis 2, and it trades UI smoothness for solve time. Decide after the
  measurement, not before.

## Tests

Written first, all running without AEDT against the existing adapter fakes:

- [test_solve_watch.py](../../tests/unit/adapters/test_solve_watch.py): the
  solve starts with `blocking=False`; the watch keeps polling while the desktop
  reports a running simulation; a desktop that never reports one still finishes
  instead of looping forever; a refused start fails without waiting; a token
  cancelled mid-solve and one cancelled up front both stop the solver and raise.
- [test_maxwell3d_solve.py](../../tests/unit/adapters/test_maxwell3d_solve.py)
  and [test_maxwell2d_solve.py](../../tests/unit/adapters/test_maxwell2d_solve.py):
  the exporter starts the solve non-blocking, and a run cancelled during
  `analyze` stops the solver, ends `cancelled`, and extracts no results.

Gate on 2026-08-10, in this working tree:

```bash
.venv/Scripts/python.exe -m pytest -n 8 -m "not aedt and not femm" -q
```

`1406 passed in 44.81s`. `ruff check .`, `mypy src tools` (142 files) and
`python -m tools.check_architecture` are clean.

Live evidence still to record on the workstation: the heartbeat gap from the
probe above before and after the change, and one run cancelled mid-solve from
the Guided Studio showing `"status": "cancelled"` in its manifest.

## Scope note

FEMM has the same shape: `PyfemmSolver` drives pyFEMM, which is a blocking
in-process COM call. If the experiment confirms hypothesis 1, FEMM should be
checked for the same freeze, but it is out of scope of this fix.
