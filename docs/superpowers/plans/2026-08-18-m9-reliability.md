# M9 Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the application survive being interrupted — by the user, by a crash, by AEDT, or by the filesystem — without ever losing the last valid Project document, without ever reporting a partial run as successful, and while producing diagnostic evidence that can leave this machine because it carries no user paths, machine names, licence servers, user names, or e-mail addresses.

**Architecture:** Four independent mechanisms, each attached to machinery that already exists. Undo/redo and autosave attach to `ProjectSession`, which is already the single writer of the in-memory project (`apply()` is the only edit path used by all five Guided Studio controllers). Autosave writes a *recovery snapshot* into the application data directory through the existing `ProjectRepository`, so it inherits schema-v5 validation and the non-finite refusal; it never touches the user's `*.inductor.json`, so the M7c disabled-until-saved `Generate` gate is unaffected. Interrupted-run recovery reconciles the durable `running` manifest that `start_project_run` already writes before dispatch, rewriting it to a new `interrupted` status — and never re-solving a run directory in place. Actionable errors come from one pure advice table consulted at the single point where manifest diagnostics are assembled. Redaction is one pure function consulted at exactly two write boundaries: the application log formatter and the diagnostic bundle builder.

**Tech Stack:** Python 3.13, PySide6/QML, `logging.handlers.RotatingFileHandler`, `zipfile`, PyAEDT against AEDT 2025 R2 Commercial, pyFEMM against FEMM 4.2, pytest with `pytest-xdist`, Ruff, strict mypy.

## Entry condition

The plan index's execution rule allows exactly one active detailed milestone plan, and M9's entry condition is M8's run and result contracts being accepted. **Fabio Posser accepted M8 on 2026-08-18.** M9 therefore consumes these as frozen contracts and does not redesign them:

- `start_project_run` in `src/inductor_designer/application/services/project_run.py`, its `runs/<run-id>-<backend>/` layout, and its `run-manifest.json`;
- `RunStatus` in `src/inductor_designer/simulation/run_contracts.py`, including `RUNNING` and `CANCELLED`;
- the `RunManifest` document produced by `run_manifest_to_document`;
- `results/solve-log.txt`, `results/results.json`, `results/results.csv`;
- the `PathOpener` port and `DesktopPathOpener`, shipped in M7b and wired to Review in M7c;
- the lowercase dotted `<quantity>.<reason>` diagnostic-code convention recorded in the plan index and used by `simulation/preliminary_contracts.py` and `simulation/result_vocabulary.py`.

Only Fabio Posser accepts a milestone. This plan ends with evidence he can verify himself.

## Global Constraints

- The only supported AEDT target is AEDT 2025 R2 Commercial.
- `domain`, `geometry`, `materials` and `simulation` import no PyAEDT, no Qt, no SQLite and no operating-system API (`os`, `pathlib`, `platform`, `shutil`, `subprocess`, `tempfile`, `winreg` included); `tools/check_architecture.py` enforces this. `application` may hold `Path` values but must not import `inductor_designer.adapters`.
- Never change a physical assumption, schema, catalog value, unit, source reference or approximation silently. M9 changes no physics: no formula, no material, no plan builder, no adapter stage list.
- Add or update tests before implementing a feature or a fix.
- A partial artifact or an interrupted analysis is never reported as successful (roadmap realignment section 8).
- Failed edits preserve the last valid Project and preview (architecture rule 12).
- Diagnostic, reason and advice codes are lowercase dotted `<subject>.<reason>` strings. Never reuse or repurpose a code; add a new one.
- **A diagnostic bundle must never carry an absolute user path, a machine name, a licence server identifier, a user name, or an e-mail address.** BRUSA policy is that no personally identifiable information leaves BRUSA systems, so the bundle is designed from the start to be shareable.
- All code, comments, commits and UI copy in English.
- Full suite: `.venv/Scripts/python.exe -m pytest -n 8`. Live suites are behind the `aedt` and `femm` markers. **M9 adds no automated live-solver test.**

## Scope

In scope, exactly the four approved ROADMAP bullets:

1. autosave, crash recovery, and application-wide undo/redo over the Project document;
2. recovering an interrupted run without claiming partial success;
3. actionable installation, license, material, file, and convergence errors;
4. redacted logs and a diagnostic bundle.

Out of scope: packaged resource discovery, PyInstaller, Inno Setup, installation detection and the clean-install checklist (all M10); any new physical quantity, any new result, any new backend, any change to the five-screen Guided Studio flow, and any MCP surface work.

## Redaction requirement

This is the security-relevant part of the milestone, so its enforcement points are named here rather than left to a task:

- **One pure function**, `redact_text(text, context)` in `src/inductor_designer/application/services/redaction.py` (Task 1), removes drive-letter paths, UNC paths, POSIX home paths, e-mail addresses, `port@host` licence server identifiers, and the machine's own user names and host names. It keeps a file extension (`[redacted-path].adp`) because the extension is the diagnostic value and names nobody.
- **Two write boundaries call it, and nothing else writes shareable text.** The application log's formatter (Task 2) redacts every record, including tracebacks, as the line is written — so the file on disk is already shareable and no caller can forget. The bundle builder (Task 8) redacts every entry's *text and name* in one loop, and the archive writer accepts only entries the builder produced.
- **Two tests prove it.** A pure test drives `redact_text` over each pattern plus idempotence (Task 1). An end-to-end test seeds a run tree with `C:\Users\jane.doe\...`, `\\BRUSA-FS01\share\model.aedt`, `1055@LICSRV01`, `jane.doe@brusa.biz`, host `BRUSA-WS42`, writes a real archive, reopens it with `zipfile`, and asserts that no entry name and no entry byte matches an independently written forbidden-pattern list (Task 8).
### Bundle contents, decided with Fabio Posser on 2026-08-18

Two rulings, both settled before implementation, so Task 8 has no open scope:

- **The Project document is excluded.** Not because it probably holds a name, but
  because nothing can prove it does not: the project name, the description, the
  winding labels and `terminal_intent` are free text, and no pattern can classify
  user prose. Including it would downgrade the bundle from provably shareable to
  probably fine. The diagnostic cost is small, because `run-manifest.json` already
  carries every physical input -- frequency, both temperatures, the material
  record, and per-winding currents, phase and direction -- keyed by `windingId`
  rather than by label. So the bundle keeps the physics and drops only the prose,
  and a user who wants to send the document attaches it deliberately.
- **AEDT's own log files are excluded, and the messages that matter are captured
  instead.** Those files are written in a format this application does not
  control, so their redaction cannot be proven by any test here, and they demonstrably
  carry BRUSA identity: the `batch.log` left by the 2026-08-18 session holds 132
  lines naming the user, the machine or the domain, including the path fragment
  `CH01NB296.brusa.biz_9996.pjt`. Copying such a file is unauditable. But the line
  that actually explained that day's failure -- `Unable to create child process:
  3dedy` -- came from the desktop *message channel*, not from a file, so Task 3
  captures those messages through this application's own redacting logger. The
  highest-value AEDT diagnostic therefore lands inside the boundary the tests
  cover, and no third-party file is ever copied.

- Logs *inside a run directory* are not redacted. They stay on the user's machine, where the absolute path is what makes them useful; redaction happens on the way into the bundle. That boundary is stated in the module docstrings so nobody later "fixes" one side.

## File Structure

| File | Responsibility |
| --- | --- |
| `src/inductor_designer/application/services/redaction.py` (create) | Pure: `RedactionContext`, `redact_text`, the redaction markers |
| `src/inductor_designer/adapters/system/environment.py` (create) | This machine: application data / recovery / log directories, and the machine's own user and host tokens |
| `src/inductor_designer/adapters/system/app_logging.py` (create) | One rotating application log whose formatter redacts every line |
| `src/inductor_designer/simulation/failure_advice.py` (create) | Pure: installation / license / material / file / convergence advice tables |
| `src/inductor_designer/adapters/pyaedt/live_app.py` (modify) | `desktop_messages()`: AEDT's session-scoped message channel |
| `src/inductor_designer/adapters/pyaedt/maxwell3d.py`, `maxwell2d.py` (modify) | Log that channel when a stage fails, before the desktop is released |
| `src/inductor_designer/application/services/maxwell_export.py` (modify) | Append advice to manifest diagnostics at the single assembly point |
| `src/inductor_designer/application/services/result_normalization.py` (modify) | Attach convergence advice to the convergence quantity |
| `src/inductor_designer/ui/project_session.py` (modify) | Undo/redo stacks, dirty-by-comparison-to-saved, autosave scheduling, recovered-project entry point |
| `src/inductor_designer/adapters/persistence/recovery_store.py` (create) | Write, read, load and clear the recovery snapshot through `ProjectRepository` |
| `src/inductor_designer/ui/recovery_controller.py` (create) | Offer / recover / discard an unsaved-changes snapshot at startup |
| `src/inductor_designer/simulation/run_contracts.py` (modify) | Add `RunStatus.INTERRUPTED` |
| `src/inductor_designer/application/services/run_recovery.py` (create) | Find and reconcile unfinished runs; never re-solve in place |
| `src/inductor_designer/ui/review_controller.py` (modify) | Interrupted-run rows and open-by-run-id |
| `src/inductor_designer/application/services/diagnostic_bundle.py` (create) | Pure: redacted bundle entries and the contents index |
| `src/inductor_designer/adapters/system/diagnostic_archive.py` (create) | Read the sources from disk; write the `.zip` |
| `src/inductor_designer/ui/diagnostics_controller.py` (create) | Help > Save diagnostic bundle |
| `src/inductor_designer/ui/qml/Main.qml` (modify) | Edit menu (Undo/Redo), Help > Save diagnostic bundle, the recovery dialog |
| `src/inductor_designer/ui/qml/ReviewPage.qml` (modify) | Render interrupted-run rows with their per-run folder button |
| `src/inductor_designer/ui/main.py` (modify) | Configure logging first, build the recovery store, reconcile unfinished runs, wire the new controllers |

---

### Task 1: Redaction rules

**Files:**
- Create: `src/inductor_designer/application/services/redaction.py`
- Test: `tests/unit/application/test_redaction.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `RedactionContext(user_names: tuple[str, ...] = (), host_names: tuple[str, ...] = ())`; `redact_text(text: str, context: RedactionContext) -> str`; the marker constants `REDACTED_EMAIL`, `REDACTED_HOST`, `REDACTED_LICENSE_SERVER`, `REDACTED_PATH`, `REDACTED_USER`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/application/test_redaction.py
from __future__ import annotations

from inductor_designer.application.services.redaction import (
    REDACTED_EMAIL,
    REDACTED_HOST,
    REDACTED_LICENSE_SERVER,
    REDACTED_PATH,
    REDACTED_USER,
    RedactionContext,
    redact_text,
)

CONTEXT = RedactionContext(
    user_names=("jane.doe", "fpo01"), host_names=("BRUSA-WS42", "brusa-ws42.brusa.biz")
)


def test_drive_letter_path_keeps_only_its_extension() -> None:
    text = r"Engine Detected Error: C:\Users\jane.doe\runs\20260818-101500\model.adp not found"
    redacted = redact_text(text, CONTEXT)
    assert "jane.doe" not in redacted
    assert "C:" not in redacted
    assert f"{REDACTED_PATH}.adp" in redacted


def test_drive_letter_path_without_extension_is_removed_entirely() -> None:
    redacted = redact_text(r"run folder: D:\work\projects\boost", CONTEXT)
    assert redacted == f"run folder: {REDACTED_PATH}"


def test_unc_path_is_removed() -> None:
    redacted = redact_text(r"saved \\BRUSA-FS01\share\model.aedt", CONTEXT)
    assert "BRUSA-FS01" not in redacted
    assert f"{REDACTED_PATH}.aedt" in redacted


def test_posix_home_path_is_removed() -> None:
    redacted = redact_text("wrote /home/jane.doe/.local/share/app.log", CONTEXT)
    assert "jane.doe" not in redacted
    assert f"{REDACTED_PATH}.log" in redacted


def test_email_address_is_removed() -> None:
    redacted = redact_text("contact jane.doe@brusa.biz for the licence", CONTEXT)
    assert redacted == f"contact {REDACTED_EMAIL} for the licence"


def test_license_server_identifier_is_removed() -> None:
    redacted = redact_text("checkout failed on 1055@LICSRV01", CONTEXT)
    assert redacted == f"checkout failed on {REDACTED_LICENSE_SERVER}"


def test_host_and_user_names_are_removed_case_insensitively() -> None:
    redacted = redact_text("session on brusa-ws42 started by JANE.DOE", CONTEXT)
    assert REDACTED_HOST in redacted
    assert REDACTED_USER in redacted
    assert "ws42" not in redacted.casefold()


def test_redaction_is_idempotent() -> None:
    text = (
        r"C:\Users\jane.doe\model.aedt jane.doe@brusa.biz 1055@LICSRV01 BRUSA-WS42"
    )
    once = redact_text(text, CONTEXT)
    assert redact_text(once, CONTEXT) == once


def test_short_tokens_are_ignored_so_ordinary_text_survives() -> None:
    context = RedactionContext(user_names=("ab",), host_names=("x",))
    assert redact_text("a stable absolute value", context) == "a stable absolute value"


def test_a_token_that_collides_with_a_marker_word_is_ignored() -> None:
    context = RedactionContext(user_names=("path",))
    assert redact_text(r"C:\tmp\a.adp", context) == f"{REDACTED_PATH}.adp"


def test_text_with_nothing_to_redact_is_returned_unchanged() -> None:
    assert redact_text("analyze: succeeded", CONTEXT) == "analyze: succeeded"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/application/test_redaction.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'inductor_designer.application.services.redaction'`

- [ ] **Step 3: Write the implementation**

```python
# src/inductor_designer/application/services/redaction.py
"""Turn diagnostic text into text that is allowed to leave this machine.

BRUSA policy is that no personally identifiable information leaves BRUSA
systems, so the diagnostic bundle is designed to be shareable rather than
sanitised afterwards. This module is the only place that decides what
"shareable" means, and exactly two writers call it: the application log
formatter (`adapters/system/app_logging.py`) and the bundle builder
(`application/services/diagnostic_bundle.py`).

A file extension deliberately survives. `[redacted-path].adp` is what makes an
AEDT ``Engine Detected Error`` about a missing ``.adp`` diagnosable, and an
extension names nobody.

Logs written inside a run directory are NOT redacted: they stay on the user's
own machine, where the absolute path is the useful part. Redaction happens on
the way into the bundle, not on the way onto disk.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

REDACTED_EMAIL = "[redacted-email]"
REDACTED_HOST = "[redacted-host]"
REDACTED_LICENSE_SERVER = "[redacted-license-server]"
REDACTED_PATH = "[redacted-path]"
REDACTED_USER = "[redacted-user]"

# E-mail first: its local part may contain a user name, and its domain would
# otherwise be left behind once the user token is replaced by a marker whose
# brackets stop the e-mail pattern from matching at all.
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_UNC_PATH = re.compile(r"\\\\[^\s\\/]+\\[^\s\"'<>|]*")
_DRIVE_PATH = re.compile(r"[A-Za-z]:[\\/][^\s\"'<>|]*")
_POSIX_HOME_PATH = re.compile(r"/(?:home|Users)/[^\s\"'<>|]*")
# FlexNet identifiers are `port@host`; the host alone identifies a BRUSA server.
_LICENSE_SERVER = re.compile(r"\b\d{1,5}@[A-Za-z0-9._-]+")
_EXTENSION = re.compile(r"\.([A-Za-z0-9]{1,6})$")

# A token equal to a word inside a marker would re-redact the marker and break
# idempotence, so those tokens are dropped rather than applied.
_MARKER_WORDS = frozenset(
    {"redacted", "path", "user", "host", "email", "license", "server"}
)
# One- and two-character tokens match inside ordinary words; a machine that
# reports such a user name is better served by the path rules alone.
_MINIMUM_TOKEN_LENGTH = 3


@dataclass(frozen=True, slots=True)
class RedactionContext:
    """Machine-specific tokens no regular expression can recognise on its own."""

    user_names: tuple[str, ...] = ()
    host_names: tuple[str, ...] = ()


def _path_replacement(match: re.Match[str]) -> str:
    # Trailing sentence punctuation is not part of the path, and would
    # otherwise be mistaken for the extension.
    extension = _EXTENSION.search(match.group(0).rstrip(".,;:)\u2019'\""))
    if extension is None:
        return REDACTED_PATH
    return f"{REDACTED_PATH}.{extension.group(1)}"


def _token_pattern(tokens: tuple[str, ...]) -> re.Pattern[str] | None:
    usable = {
        token
        for token in tokens
        if len(token) >= _MINIMUM_TOKEN_LENGTH and token.casefold() not in _MARKER_WORDS
    }
    if not usable:
        return None
    # Longest first, so a fully qualified host name is replaced as one token
    # rather than leaving its domain behind.
    ordered = sorted(usable, key=len, reverse=True)
    return re.compile("|".join(re.escape(token) for token in ordered), re.IGNORECASE)


def redact_text(text: str, context: RedactionContext) -> str:
    """Remove every shareability hazard. Idempotent by construction."""
    redacted = _EMAIL.sub(REDACTED_EMAIL, text)
    redacted = _UNC_PATH.sub(_path_replacement, redacted)
    redacted = _DRIVE_PATH.sub(_path_replacement, redacted)
    redacted = _POSIX_HOME_PATH.sub(_path_replacement, redacted)
    redacted = _LICENSE_SERVER.sub(REDACTED_LICENSE_SERVER, redacted)
    hosts = _token_pattern(context.host_names)
    if hosts is not None:
        redacted = hosts.sub(REDACTED_HOST, redacted)
    users = _token_pattern(context.user_names)
    if users is not None:
        redacted = users.sub(REDACTED_USER, redacted)
    return redacted
```

- [ ] **Step 4: Run the tests and the architecture check**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/application/test_redaction.py -q`
Expected: PASS, 11 tests

Run: `.venv/Scripts/python.exe -m tools.check_architecture`
Expected: clean exit, no output

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/application/services/redaction.py tests/unit/application/test_redaction.py
git commit -m "feat(diagnostics): add the one redaction rule set shared logs and bundles use"
```

---

### Task 2: Redacted application log

**Files:**
- Create: `src/inductor_designer/adapters/system/environment.py`
- Create: `src/inductor_designer/adapters/system/app_logging.py`
- Modify: `src/inductor_designer/ui/main.py:166-180` (inside `main()`, before the `QGuiApplication` is created)
- Test: `tests/unit/adapters/system/test_app_logging.py`

**Interfaces:**
- Consumes: `RedactionContext`, `redact_text` from Task 1.
- Produces: `application_data_directory() -> Path`, `recovery_directory() -> Path`, `log_directory() -> Path`, `environment_redaction_context() -> RedactionContext` in `adapters/system/environment.py`; `LOGGER_NAME = "inductor_designer"`, `APP_LOG_FILENAME = "inductor-designer.log"`, `RedactingFormatter`, `configure_application_logging(directory: Path, context: RedactionContext) -> Path` in `adapters/system/app_logging.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/adapters/system/test_app_logging.py
from __future__ import annotations

import logging
from pathlib import Path

from inductor_designer.adapters.system.app_logging import (
    APP_LOG_FILENAME,
    LOGGER_NAME,
    configure_application_logging,
)
from inductor_designer.adapters.system.environment import (
    application_data_directory,
    environment_redaction_context,
    log_directory,
    recovery_directory,
)
from inductor_designer.application.services.redaction import (
    REDACTED_PATH,
    RedactionContext,
)


def test_directories_are_nested_under_one_application_directory() -> None:
    root = application_data_directory()
    assert recovery_directory().parent == root
    assert log_directory().parent == root


def test_environment_context_reports_this_machine() -> None:
    context = environment_redaction_context()
    assert isinstance(context, RedactionContext)
    # A machine always has at least one of the two; an empty context would
    # silently disable token redaction.
    assert context.user_names or context.host_names


def test_log_line_is_written_redacted(tmp_path: Path) -> None:
    path = configure_application_logging(
        tmp_path, RedactionContext(user_names=("jane.doe",))
    )
    logging.getLogger(LOGGER_NAME).warning(r"save failed: C:\Users\jane.doe\b.json")
    logging.shutdown()

    written = path.read_text(encoding="utf-8")
    assert path.name == APP_LOG_FILENAME
    assert "jane.doe" not in written
    assert f"{REDACTED_PATH}.json" in written
    assert "WARNING" in written


def test_traceback_text_is_written_redacted(tmp_path: Path) -> None:
    path = configure_application_logging(
        tmp_path, RedactionContext(user_names=("jane.doe",))
    )
    try:
        raise OSError(r"cannot open C:\Users\jane.doe\model.aedt")
    except OSError:
        logging.getLogger(LOGGER_NAME).exception("autosave failed")
    logging.shutdown()

    written = path.read_text(encoding="utf-8")
    assert "jane.doe" not in written
    assert "OSError" in written


def test_configuring_twice_does_not_duplicate_handlers(tmp_path: Path) -> None:
    configure_application_logging(tmp_path, RedactionContext())
    configure_application_logging(tmp_path, RedactionContext())
    assert len(logging.getLogger(LOGGER_NAME).handlers) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/adapters/system/test_app_logging.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'inductor_designer.adapters.system.app_logging'`

- [ ] **Step 3: Write the implementation**

```python
# src/inductor_designer/adapters/system/environment.py
"""What this machine is, and where the application keeps its private state.

A Project document is shareable and its directory belongs to the user, so the
recovery snapshot and the application log live outside it -- an autosave must
never appear as a stray file next to a project a user is about to send to a
colleague.
"""

from __future__ import annotations

import contextlib
import getpass
import os
import platform
from pathlib import Path

from inductor_designer.application.services.redaction import RedactionContext

APPLICATION_DIRECTORY_NAME = "InductorDesigner"


def application_data_directory() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    # Windows is the product platform (ADR 0004). The fallback exists only so
    # the non-solver suite runs on the Linux CI runner.
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / APPLICATION_DIRECTORY_NAME


def recovery_directory() -> Path:
    return application_data_directory() / "recovery"


def log_directory() -> Path:
    return application_data_directory() / "logs"


def environment_redaction_context() -> RedactionContext:
    """The user and host tokens no regular expression can recognise."""
    users = {
        name
        for name in (os.environ.get("USERNAME"), os.environ.get("USER"))
        if name
    }
    with contextlib.suppress(Exception):
        # getpass consults the password database on POSIX and can raise there.
        users.add(getpass.getuser())
    with contextlib.suppress(Exception):
        users.add(Path.home().name)
    hosts = {
        name
        for name in (os.environ.get("COMPUTERNAME"), platform.node())
        if name
    }
    # A node may be reported fully qualified; its first label identifies the
    # machine on its own, so both forms are redacted.
    hosts |= {name.split(".")[0] for name in tuple(hosts)}
    return RedactionContext(
        user_names=tuple(sorted(users)), host_names=tuple(sorted(hosts))
    )
```

```python
# src/inductor_designer/adapters/system/app_logging.py
"""One rotating application log, redacted as each line is written.

Redacting in the formatter rather than at the call site is what makes the file
shareable by construction: no caller can forget, tracebacks are covered by the
same pass, and the log the user finds on disk is exactly the text the
diagnostic bundle carries.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from inductor_designer.application.services.redaction import (
    RedactionContext,
    redact_text,
)

LOGGER_NAME = "inductor_designer"
APP_LOG_FILENAME = "inductor-designer.log"
_FORMAT = "%(asctime)s\t%(levelname)s\t%(name)s\t%(message)s"
_MAX_BYTES = 1_000_000
_BACKUP_COUNT = 2


class RedactingFormatter(logging.Formatter):
    """Formats the record, then redacts the whole rendered line."""

    def __init__(self, context: RedactionContext) -> None:
        super().__init__(_FORMAT)
        self._context = context

    def format(self, record: logging.LogRecord) -> str:
        return redact_text(super().format(record), self._context)


def configure_application_logging(
    directory: Path, context: RedactionContext
) -> Path:
    """Install the single redacting handler and return the log file path."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / APP_LOG_FILENAME
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    # Replace rather than append: a second call (a test, a restarted session in
    # the same process) must not double every line.
    for existing in list(logger.handlers):
        logger.removeHandler(existing)
        existing.close()
    handler = RotatingFileHandler(
        path,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
        delay=True,
    )
    handler.setFormatter(RedactingFormatter(context))
    logger.addHandler(handler)
    # The root logger has no redacting handler, so nothing may escape upwards.
    logger.propagate = False
    return path
```

In `src/inductor_designer/ui/main.py`, at the top of `main()` before `QGuiApplication` is constructed:

```python
    from inductor_designer.adapters.system.app_logging import (
        LOGGER_NAME,
        configure_application_logging,
    )
    from inductor_designer.adapters.system.environment import (
        environment_redaction_context,
        log_directory,
    )

    redaction_context = environment_redaction_context()
    log_path = configure_application_logging(log_directory(), redaction_context)
    logger = logging.getLogger(LOGGER_NAME)
    logger.info("Application %s starting.", __version__)
```

- [ ] **Step 4: Add the log calls at the reliability points**

Log at INFO on: application start, project opened, project saved, recovery snapshot restored, run started, run finished with its status, unfinished run reconciled. Log at WARNING on: save failure, autosave failure, recovery read failure, run failure with its manifest diagnostics. Use `logging.getLogger(LOGGER_NAME)` in `ui/project_session.py`, `ui/generation_controller.py` and `ui/recovery_controller.py`; keep the existing `set_status` messages exactly as they are — the log is additional evidence, not a replacement for the visible message.

- [ ] **Step 5: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/adapters/system -q`
Expected: PASS

Run: `.venv/Scripts/python.exe -m tools.check_architecture`
Expected: clean exit, no output

- [ ] **Step 6: Commit**

```bash
git add src/inductor_designer/adapters/system src/inductor_designer/ui/main.py tests/unit/adapters/system
git commit -m "feat(diagnostics): write one rotating application log, redacted as it is written"
```

---

### Task 3: Actionable installation, license, material, file and convergence errors

**Files:**
- Create: `src/inductor_designer/simulation/failure_advice.py`
- Modify: `src/inductor_designer/application/services/maxwell_export.py:492-537` (`_build_manifest`)
- Modify: `src/inductor_designer/application/services/result_normalization.py:344-367,419-428` (`_convergence`, `normalize_scalar_results`)
- Modify: `src/inductor_designer/adapters/pyaedt/live_app.py` (`desktop_messages`)
- Modify: `src/inductor_designer/adapters/pyaedt/maxwell3d.py` and `maxwell2d.py` (log those messages when a stage fails, before the desktop is released)
- Test: `tests/unit/simulation/test_failure_advice.py`
- Test: `tests/unit/application/test_diagnostic_advice.py`
- Test: `tests/unit/adapters/pyaedt/test_desktop_message_capture.py`

**Interfaces:**
- Consumes: nothing outside `domain`/`simulation` for the advice table; `LOGGER_NAME` (Task 2) for the capture.
- Produces: `AdviceCode` with the string constants below; `FailureAdvice(code: str, action: str)`; `advise(diagnostic: str) -> FailureAdvice`; `convergence_advice(*, final_error_percent: float, target_percent: float | None, completed_passes: int, maximum_passes: int | None, converged: bool | None) -> FailureAdvice | None`. `normalize_scalar_results` gains keyword-only `percent_error_target: float | None = None` and `maximum_passes: int | None = None`. On `LiveAppExtraction`: `desktop_messages(self) -> tuple[str, ...]`.

#### The desktop message channel is captured; AEDT's log files are not

Decided with Fabio Posser on 2026-08-18, out of that day's evidence. The lines that
explained a failed solve --- `Unable to create child process: 3dedy`, then
`Simulation completed with execution error on server: Local Machine` --- exist only
in AEDT's message channel. Nothing this application wrote said why the solve died.

A failed stage therefore captures that channel into the application log, where
Task 2's formatter redacts it like every other line. AEDT's own log files stay out
of the bundle (see the bundle-contents decision above); this is what replaces
them, and it is auditable because this application writes it.

Two load-bearing constraints:

- **The channel is session-scoped.** `release_live_app(app)` at
  `adapters/pyaedt/maxwell3d.py:687` ends the session and the messages die with it,
  so capture belongs at the stage-failure boundary --- the `except Exception`
  handlers around `maxwell3d.py:582-660` and their 2D counterparts --- and never in
  the application layer, which holds no desktop.
- **Capture must never turn one failure into another.** A read that raises is
  swallowed and noted; the run still reports the original error. Same rule the
  result reader already follows.

The captured text goes to the log, not into `StageRecord.message`: a message
channel can run to hundreds of lines and `run-manifest.json` is a document a
person reads.

- [ ] **Step 0: `desktop_messages`, and the capture at the failure boundary**

```python
# src/inductor_designer/adapters/pyaedt/live_app.py
    def desktop_messages(self) -> tuple[str, ...]:
        """AEDT's own message channel for this design, oldest first.

        The only place a solver's reason for dying is stated: on 2026-08-18 a run
        was recorded `succeeded` while this channel held "Unable to create child
        process: 3dedy". Session-scoped, so it must be read before the desktop is
        released.
        """
        try:
            messages = self._app.odesktop.GetMessages(
                self._app.project_name, self._app.design_name, 0
            )
        except Exception:  # noqa: BLE001 - a silent channel is not a failure
            return ()
        return tuple(str(line) for line in messages or ())
```

```python
# src/inductor_designer/adapters/pyaedt/maxwell3d.py, called from each stage-failure handler
def _log_desktop_messages(app: Maxwell3dApp, stage: str) -> None:
    """Record why AEDT failed, while the session that knows still exists."""
    logger = logging.getLogger(LOGGER_NAME)
    try:
        messages = app.desktop_messages()
    except Exception as error:  # noqa: BLE001 - capture never masks the real failure
        logger.warning("Could not read AEDT messages after %s failed: %s", stage, error)
        return
    for line in messages:
        logger.error("AEDT [%s]: %s", stage, line)
```

Verify: `pytest tests/unit/adapters/pyaedt/test_desktop_message_capture.py -q` proves
that a failed stage writes every channel line to the log, that a raising channel
leaves the original stage error intact and the run's own diagnostic unchanged, and
that the lines reach the log through the redacting formatter rather than around it.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/simulation/test_failure_advice.py
from __future__ import annotations

from inductor_designer.simulation.failure_advice import (
    AdviceCode,
    advise,
    convergence_advice,
)


def test_missing_pyaedt_is_an_installation_problem() -> None:
    advice = advise("No module named 'ansys.aedt.core'")
    assert advice.code == AdviceCode.INSTALLATION_PYAEDT_MISSING
    assert "pip install" in advice.action


def test_missing_femm_is_an_installation_problem() -> None:
    advice = advise("No module named 'femm'")
    assert advice.code == AdviceCode.INSTALLATION_FEMM_MISSING


def test_unreachable_desktop_is_an_installation_problem() -> None:
    advice = advise("Failed to connect to AEDT: Desktop is not running.")
    assert advice.code == AdviceCode.INSTALLATION_AEDT_NOT_REACHABLE


def test_license_text_is_a_license_problem() -> None:
    advice = advise("License checkout failed: no license available for Maxwell")
    assert advice.code == AdviceCode.LICENSE_UNAVAILABLE


def test_flexlm_server_text_names_the_licence_server() -> None:
    advice = advise("FlexNet error -15: cannot connect to license server")
    assert advice.code == AdviceCode.LICENSE_SERVER_UNREACHABLE


def test_missing_solver_data_file_names_the_never_re_solve_rule() -> None:
    advice = advise(
        "Engine Detected Error: Failed to open project file model.adp"
    )
    assert advice.code == AdviceCode.FILE_MISSING_SOLVER_DATA
    assert "new run" in advice.action.casefold()


def test_locked_file_is_a_file_problem() -> None:
    advice = advise("The process cannot access the file because it is being used")
    assert advice.code == AdviceCode.FILE_LOCKED


def test_denied_file_is_a_file_problem() -> None:
    advice = advise("PermissionError: [Errno 13] Permission denied")
    assert advice.code == AdviceCode.FILE_PERMISSION_DENIED


def test_material_text_is_a_material_problem() -> None:
    advice = advise("Invalid permeability dataset for material N87")
    assert advice.code == AdviceCode.MATERIAL_REJECTED_BY_SOLVER


def test_unrecognised_text_is_honestly_unclassified() -> None:
    advice = advise("something nobody has seen before")
    assert advice.code == AdviceCode.UNCLASSIFIED
    assert advice.action


def test_first_match_wins_so_a_licence_file_error_is_a_licence_error() -> None:
    advice = advise("Cannot open license file: permission denied")
    assert advice.code == AdviceCode.LICENSE_UNAVAILABLE


def test_a_converged_run_needs_no_convergence_advice() -> None:
    assert (
        convergence_advice(
            final_error_percent=0.4,
            target_percent=1.0,
            completed_passes=3,
            maximum_passes=10,
            converged=True,
        )
        is None
    )


def test_pass_limit_advice_when_the_solver_ran_out_of_passes() -> None:
    advice = convergence_advice(
        final_error_percent=4.0,
        target_percent=1.0,
        completed_passes=10,
        maximum_passes=10,
        converged=False,
    )
    assert advice is not None
    assert advice.code == AdviceCode.CONVERGENCE_PASS_LIMIT


def test_target_missed_advice_when_passes_remained() -> None:
    advice = convergence_advice(
        final_error_percent=4.0,
        target_percent=1.0,
        completed_passes=4,
        maximum_passes=10,
        converged=False,
    )
    assert advice is not None
    assert advice.code == AdviceCode.CONVERGENCE_NOT_REACHED


def test_no_target_and_no_state_produces_no_claim() -> None:
    assert (
        convergence_advice(
            final_error_percent=4.0,
            target_percent=None,
            completed_passes=4,
            maximum_passes=None,
            converged=None,
        )
        is None
    )
```

```python
# tests/unit/application/test_diagnostic_advice.py
"""Advice must reach the manifest, next to the raw diagnostic, never instead of it."""

from __future__ import annotations

from inductor_designer.application.services.maxwell_export import _with_advice
from inductor_designer.simulation.failure_advice import AdviceCode


def test_advice_is_appended_after_each_diagnostic() -> None:
    advised = _with_advice(("License checkout failed: no license available",))
    assert advised[0] == "License checkout failed: no license available"
    assert advised[1].startswith(f"{AdviceCode.LICENSE_UNAVAILABLE}: ")


def test_no_diagnostics_stay_no_diagnostics() -> None:
    assert _with_advice(()) == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/simulation/test_failure_advice.py tests/unit/application/test_diagnostic_advice.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'inductor_designer.simulation.failure_advice'`

- [ ] **Step 3: Write the implementation**

```python
# src/inductor_designer/simulation/failure_advice.py
"""What to do about a failure, keyed on the text the solver actually produced.

Advice is always appended to the raw diagnostic, never substituted for it: the
raw text is the evidence and the advice is the reading of it. Text nobody has
classified yet returns `run.unclassified_failure`, which says so honestly
rather than guessing.

The match substrings below are the observed wording of AEDT 2025 R2, pyFEMM
4.2 and the Python standard library as of 2026-08-18. A substring that stops
matching costs the advice line, never the diagnostic, so a wrong entry here
cannot turn a failure into a success.
"""

from __future__ import annotations

from dataclasses import dataclass


class AdviceCode:
    """Stable lowercase dotted `<subject>.<reason>` advice codes."""

    INSTALLATION_PYAEDT_MISSING = "installation.pyaedt_missing"
    INSTALLATION_FEMM_MISSING = "installation.femm_missing"
    INSTALLATION_AEDT_NOT_REACHABLE = "installation.aedt_not_reachable"
    LICENSE_UNAVAILABLE = "license.unavailable"
    LICENSE_SERVER_UNREACHABLE = "license.server_unreachable"
    MATERIAL_REJECTED_BY_SOLVER = "material.rejected_by_solver"
    FILE_PERMISSION_DENIED = "file.permission_denied"
    FILE_LOCKED = "file.locked"
    FILE_MISSING_SOLVER_DATA = "file.missing_solver_data"
    CONVERGENCE_NOT_REACHED = "convergence.not_reached"
    CONVERGENCE_PASS_LIMIT = "convergence.pass_limit_reached"
    UNCLASSIFIED = "run.unclassified_failure"


@dataclass(frozen=True, slots=True)
class FailureAdvice:
    code: str
    action: str


# First match wins, so the more specific subject is listed first. A licence
# file that cannot be opened is a licence problem, not a file problem.
_RULES: tuple[tuple[str, str, str], ...] = (
    (
        "license file",
        AdviceCode.LICENSE_UNAVAILABLE,
        "AEDT could not read its licence configuration. Open Ansys License "
        "Settings, confirm the licence server entry, and run the design again.",
    ),
    (
        "license server",
        AdviceCode.LICENSE_SERVER_UNREACHABLE,
        "The licence server did not answer. Confirm network access to the "
        "Ansys licence server, then run the design again.",
    ),
    (
        "flexnet",
        AdviceCode.LICENSE_SERVER_UNREACHABLE,
        "The licence server did not answer. Confirm network access to the "
        "Ansys licence server, then run the design again.",
    ),
    (
        "no license available",
        AdviceCode.LICENSE_UNAVAILABLE,
        "No Maxwell licence was free. Wait for a licence to be released, or "
        "ask the licence administrator, then run the design again.",
    ),
    (
        "license",
        AdviceCode.LICENSE_UNAVAILABLE,
        "AEDT reported a licensing problem. Check the Ansys licence status, "
        "then run the design again.",
    ),
    (
        "no module named 'ansys",
        AdviceCode.INSTALLATION_PYAEDT_MISSING,
        "PyAEDT is not installed in this interpreter. Install it with "
        "`pip install pyaedt` into the same environment that runs the "
        "application.",
    ),
    (
        "no module named 'femm",
        AdviceCode.INSTALLATION_FEMM_MISSING,
        "pyFEMM is not installed, or FEMM 4.2 is not present. Install FEMM "
        "4.2 and `pip install pyfemm`, or choose a Maxwell backend.",
    ),
    (
        "is not installed",
        AdviceCode.INSTALLATION_AEDT_NOT_REACHABLE,
        "AEDT 2025 R2 Commercial was not found. Install it, or select a "
        "backend that does not need it.",
    ),
    (
        "failed to connect",
        AdviceCode.INSTALLATION_AEDT_NOT_REACHABLE,
        "The application could not reach an AEDT session. Close any AEDT "
        "window and any leftover ansysedt.exe process, then run again: only "
        "one AEDT session may be active.",
    ),
    (
        "desktop is not running",
        AdviceCode.INSTALLATION_AEDT_NOT_REACHABLE,
        "The AEDT desktop stopped before the run finished. Close any leftover "
        "ansysedt.exe process and start a new run.",
    ),
    (
        ".adp",
        AdviceCode.FILE_MISSING_SOLVER_DATA,
        "AEDT could not read the solver data of this project. A run directory "
        "written by an interrupted session cannot be solved again in place: "
        "start a new run, which gets its own directory.",
    ),
    (
        "engine detected error",
        AdviceCode.FILE_MISSING_SOLVER_DATA,
        "The AEDT solver engine rejected the project files. Start a new run "
        "rather than solving this directory again.",
    ),
    (
        "being used",
        AdviceCode.FILE_LOCKED,
        "Another program holds the file. Close AEDT, FEMM or the file "
        "explorer that has it open, then start a new run.",
    ),
    (
        "permission denied",
        AdviceCode.FILE_PERMISSION_DENIED,
        "The application may not write there. Save the project into a "
        "writable folder, then start a new run.",
    ),
    (
        "access is denied",
        AdviceCode.FILE_PERMISSION_DENIED,
        "The application may not write there. Save the project into a "
        "writable folder, then start a new run.",
    ),
    (
        "permeability",
        AdviceCode.MATERIAL_REJECTED_BY_SOLVER,
        "The solver rejected the pinned material data. Open Material Studio, "
        "confirm the B-H series for the requested temperature, and pin a "
        "revision the solver accepts.",
    ),
    (
        "material",
        AdviceCode.MATERIAL_REJECTED_BY_SOLVER,
        "The solver rejected the pinned material. Open Material Studio and "
        "confirm the pinned revision and its B-H series.",
    ),
)

_UNCLASSIFIED_ACTION = (
    "The failure text is not one this application recognises. Keep the run "
    "directory and attach a diagnostic bundle when reporting it."
)


def advise(diagnostic: str) -> FailureAdvice:
    """The action for one raw diagnostic. Never raises, never returns None."""
    lowered = diagnostic.casefold()
    for needle, code, action in _RULES:
        if needle in lowered:
            return FailureAdvice(code=code, action=action)
    return FailureAdvice(code=AdviceCode.UNCLASSIFIED, action=_UNCLASSIFIED_ACTION)


def convergence_advice(
    *,
    final_error_percent: float,
    target_percent: float | None,
    completed_passes: int,
    maximum_passes: int | None,
    converged: bool | None,
) -> FailureAdvice | None:
    """Advice for a solve that finished without meeting its own target.

    Returns None when the solve converged, or when neither a target nor a
    reported state supports any claim: an unproven "did not converge" would be
    a worse diagnostic than silence.
    """
    if converged is True:
        return None
    target_missed = target_percent is not None and final_error_percent > target_percent
    if not target_missed and converged is not False:
        return None
    if maximum_passes is not None and completed_passes >= maximum_passes:
        return FailureAdvice(
            code=AdviceCode.CONVERGENCE_PASS_LIMIT,
            action=(
                f"The solve used all {maximum_passes} adaptive passes and "
                f"ended at {final_error_percent:g} percent error. Raise the "
                "maximum passes, relax the percent error target, or refine "
                "the mesh intent, then run again."
            ),
        )
    return FailureAdvice(
        code=AdviceCode.CONVERGENCE_NOT_REACHED,
        action=(
            f"The solve ended at {final_error_percent:g} percent error "
            "without meeting its target. Treat the reported values as "
            "unconverged, refine the mesh intent or relax the target, then "
            "run again."
        ),
    )
```

In `maxwell_export.py`, add the helper next to `_build_manifest` and use it for the one `diagnostics=` argument:

```python
def _with_advice(diagnostics: tuple[str, ...]) -> tuple[str, ...]:
    """Each raw diagnostic, then its advice line. One assembly point, so every
    backend and every failure path gets the same treatment."""
    advised: list[str] = []
    for diagnostic in diagnostics:
        advice = advise(diagnostic)
        advised.append(diagnostic)
        advised.append(f"{advice.code}: {advice.action}")
    return tuple(advised)
```

and inside `_build_manifest`, replace `diagnostics=diagnostics,` with `diagnostics=_with_advice(diagnostics),`.

In `result_normalization.py`, widen `normalize_scalar_results` with the two keyword-only parameters, pass them to `_convergence`, and attach the advice as the quantity's approximation note:

```python
def _convergence(
    raw: RawScalarResults,
    provenance: str,
    *,
    percent_error_target: float | None = None,
    maximum_passes: int | None = None,
) -> NormalizedQuantity:
    convergence = raw.convergence
    if convergence is None or not convergence.passes:
        return _missing(
            RequestedOutput.CONVERGENCE,
            DEVICE_SCOPE,
            raw,
            "The backend reported no convergence history.",
            code=NOT_EXPOSED,
        )
    final_pass, final_error = convergence.passes[-1]
    state = (
        "converged"
        if convergence.converged
        else "did not converge"
        if convergence.converged is False
        else "convergence state not reported"
    )
    advice = convergence_advice(
        final_error_percent=final_error,
        target_percent=percent_error_target,
        completed_passes=final_pass,
        maximum_passes=maximum_passes,
        converged=convergence.converged,
    )
    return _available(
        RequestedOutput.CONVERGENCE,
        DEVICE_SCOPE,
        final_error,
        f"{provenance}: {final_pass} passes, {state}",
        # An unconverged solve stays AVAILABLE: the number is real, and the
        # note is what stops it being read as a converged number.
        approximation=None if advice is None else f"{advice.code}: {advice.action}",
    )
```

In `maxwell_export._normalized_results`, pass `percent_error_target=project.simulation_recipe.percent_error` and `maximum_passes=project.simulation_recipe.maximum_passes` into `normalize_scalar_results`.

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/simulation tests/unit/application -q`
Expected: PASS. The golden Generate Only manifests in `tests/golden/` are unchanged: those runs succeed, so their `diagnostics` list is empty and `_with_advice(())` returns `()`.

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/simulation/failure_advice.py src/inductor_designer/application tests/unit/simulation/test_failure_advice.py tests/unit/application/test_diagnostic_advice.py
git commit -m "feat(diagnostics): name the action for installation, licence, material, file and convergence failures"
```

---

### Task 4: Application-wide undo and redo

**Files:**
- Modify: `src/inductor_designer/ui/project_session.py:20-160`
- Modify: `src/inductor_designer/ui/qml/Main.qml:28-88` (menu bar)
- Test: `tests/ui/test_project_session_undo.py`
- Test: `tests/ui/test_app_menu.py` (extend)

**Interfaces:**
- Consumes: nothing new.
- Produces: on `ProjectSession`: `undoStackChanged` signal; `canUndo` and `canRedo` `Property(bool)`; `@Slot(result=bool) undo()`; `@Slot(result=bool) redo()`; `UNDO_DEPTH` module constant. `apply()`, `saveProject()`, `saveProjectAs()` and `openProject()` keep their current signatures and observable behaviour.

**Why this is the whole of "application-wide":** every Guided Studio edit already routes through `ProjectSession.apply()` — `core_material_controller.py:167`, `guided_studio_controller.py:350,411,476,528`, and `simulation_controller.py:233` are the only writers. `InductorProject` is a frozen dataclass aggregate, so one bounded list of previous project values is a complete undo history for core, material pin, windings, operating point and simulation recipe alike. No command objects, no per-screen stacks.

**How it interacts with the M7c `Generate` gate:** `SimulationController._gate()` refuses to run while `session.dirty` is true. Dirty stops being a one-way flag and becomes a comparison against the project that is actually on disk, so undoing back to the saved state re-enables `Generate` — and any other undo state leaves it correctly disabled. Nothing in the gate changes.

**Out of undo scope, stated so nobody widens it silently:** `Open`, `Save`, `Save As`, and every Material Studio library operation (import, replace, delete). A material import is an immutable library revision, not a project edit; pinning that revision into the project *is* a project edit and is undoable, because pinning goes through `apply()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/ui/test_project_session_undo.py
from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.ui.project_session import UNDO_DEPTH, ProjectSession  # noqa: E402
from tests.unit.domain.test_project import make_project  # noqa: E402

pytestmark = pytest.mark.ui


def _session(**kwargs: object) -> ProjectSession:
    QGuiApplication.instance() or QGuiApplication([])
    return ProjectSession(make_project(), **kwargs)  # type: ignore[arg-type]


def test_a_fresh_session_can_neither_undo_nor_redo() -> None:
    session = _session()
    assert session.canUndo is False
    assert session.canRedo is False
    assert session.undo() is False
    assert session.redo() is False


def test_undo_restores_the_previous_project_and_enables_redo() -> None:
    session = _session()
    session.apply(replace(session.project, description="first"))
    session.apply(replace(session.project, description="second"))

    assert session.undo() is True
    assert session.project.description == "first"
    assert session.canRedo is True
    assert session.redo() is True
    assert session.project.description == "second"


def test_undo_emits_project_changed_so_every_screen_refreshes() -> None:
    session = _session()
    session.apply(replace(session.project, description="edited"))
    changes: list[int] = []
    session.projectChanged.connect(lambda: changes.append(1))

    session.undo()

    assert changes == [1]


def test_a_new_edit_after_undo_clears_the_redo_history() -> None:
    session = _session()
    session.apply(replace(session.project, description="first"))
    session.undo()
    session.apply(replace(session.project, description="other"))

    assert session.canRedo is False


def test_undo_back_to_the_saved_project_clears_dirty(tmp_path: Path) -> None:
    path = tmp_path / "boost.inductor.json"
    path.write_text("{}", encoding="utf-8")
    session = _session(document_path=path, save_callback=lambda project: None)
    session.saveProject()
    session.apply(replace(session.project, description="edited"))
    assert session.dirty is True

    session.undo()

    assert session.dirty is False


def test_undo_history_is_bounded(tmp_path: Path) -> None:
    session = _session()
    for index in range(UNDO_DEPTH + 10):
        session.apply(replace(session.project, description=f"edit {index}"))

    undone = 0
    while session.undo():
        undone += 1

    assert undone == UNDO_DEPTH


def test_opening_a_project_clears_the_history(tmp_path: Path) -> None:
    opened = replace(make_project(), description="from disk")
    session = _session(open_callback=lambda path: opened)
    session.apply(replace(session.project, description="edited"))

    from PySide6.QtCore import QUrl

    assert session.openProject(QUrl.fromLocalFile(str(tmp_path / "other.json"))) is True
    assert session.canUndo is False
    assert session.canRedo is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `set QT_QPA_PLATFORM=offscreen && .venv/Scripts/python.exe -m pytest tests/ui/test_project_session_undo.py -q`
Expected: FAIL, `ImportError: cannot import name 'UNDO_DEPTH'`

- [ ] **Step 3: Write the implementation**

In `src/inductor_designer/ui/project_session.py`, add the module constant and the history:

```python
# Deep enough to cover a working session's edits, bounded so a long session
# cannot grow the process without limit. Each entry is one immutable project.
UNDO_DEPTH = 50
```

In `__init__`, after `self._provider = CurrentProjectProvider(project)`:

```python
        self._undo: list[InductorProject] = []
        self._redo: list[InductorProject] = []
        # The project as it exists on disk, or None when nothing has been
        # written yet. `dirty` is a comparison against this, not a flag: an
        # undo back to the saved state must re-enable the M7c Generate gate.
        self._saved_project: InductorProject | None = (
            project if document_path is not None else None
        )
```

Add the signal `undoStackChanged = Signal()` beside the existing signals, and replace `apply`, plus the dirty handling:

```python
    def apply(self, project: InductorProject) -> None:
        """Accept an already-validated edit as the current session project."""
        self._push_undo(self._provider.current())
        self._redo.clear()
        self._provider.replace(project)
        self._refresh_dirty()
        self.undoStackChanged.emit()
        self.projectChanged.emit()

    def _push_undo(self, project: InductorProject) -> None:
        self._undo.append(project)
        if len(self._undo) > UNDO_DEPTH:
            del self._undo[0]

    def _refresh_dirty(self) -> None:
        self._set_dirty(self._provider.current() != self._saved_project)

    @Slot(result=bool)
    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self._provider.current())
        self._provider.replace(self._undo.pop())
        self._refresh_dirty()
        self.undoStackChanged.emit()
        self.projectChanged.emit()
        self.set_status("Undid the last edit")
        return True

    @Slot(result=bool)
    def redo(self) -> bool:
        if not self._redo:
            return False
        self._push_undo(self._provider.current())
        self._provider.replace(self._redo.pop())
        self._refresh_dirty()
        self.undoStackChanged.emit()
        self.projectChanged.emit()
        self.set_status("Redid the last undone edit")
        return True

    def _get_can_undo(self) -> bool:
        return bool(self._undo)

    canUndo = Property(bool, _get_can_undo, notify=undoStackChanged)

    def _get_can_redo(self) -> bool:
        return bool(self._redo)

    canRedo = Property(bool, _get_can_redo, notify=undoStackChanged)
```

In `saveProject` and `saveProjectAs`, replace `self._set_dirty(False)` with:

```python
        self._saved_project = self.project
        self._refresh_dirty()
```

In `openProject`, after `self._provider.replace(project)`:

```python
        # An Open is not an edit: the history of the previous document must not
        # be able to overwrite the newly opened one.
        self._undo.clear()
        self._redo.clear()
        self._saved_project = project
```

and replace its `self._set_dirty(False)` with `self._refresh_dirty()`, then emit `self.undoStackChanged.emit()` beside the existing emits.

In `src/inductor_designer/ui/qml/Main.qml`, add an `Edit` menu between `File` and `Help`:

```qml
        Menu {
            objectName: "editMenu"
            title: qsTr("Edit")

            MenuItem {
                objectName: "undoMenuItem"
                text: qsTr("Undo")
                enabled: projectSession !== null && projectSession.canUndo
                Accessible.name: text
                Accessible.description: enabled ? "" : qsTr(
                    "Undo is unavailable: there is no earlier project edit to return to."
                )
                onTriggered: projectSession.undo()
            }
            MenuItem {
                objectName: "redoMenuItem"
                text: qsTr("Redo")
                enabled: projectSession !== null && projectSession.canRedo
                Accessible.name: text
                Accessible.description: enabled ? "" : qsTr(
                    "Redo is unavailable: nothing has been undone."
                )
                onTriggered: projectSession.redo()
            }
        }
```

- [ ] **Step 4: Run the tests**

Run: `set QT_QPA_PLATFORM=offscreen && set QSG_RHI_BACKEND=software && .venv/Scripts/python.exe -m pytest tests/ui -q`
Expected: PASS, including the existing `tests/ui/test_project_session.py`, `test_app_menu.py`, `test_simulation_controller.py` and `test_main_close_dialog.py`

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/ui/project_session.py src/inductor_designer/ui/qml/Main.qml tests/ui
git commit -m "feat(ui): undo and redo every project edit from one session history"
```

---

### Task 5: Autosave into a recovery snapshot

**Files:**
- Create: `src/inductor_designer/adapters/persistence/recovery_store.py`
- Modify: `src/inductor_designer/ui/project_session.py` (autosave scheduling)
- Modify: `src/inductor_designer/ui/main.py` (build the store, bind the callback)
- Test: `tests/unit/adapters/persistence/test_recovery_store.py`
- Test: `tests/ui/test_autosave.py`

**Interfaces:**
- Consumes: `ProjectRepository`, `SchemaRepository`, `recovery_directory()` from Task 2, `UNDO_DEPTH`/`apply`/`undo`/`redo` from Task 4.
- Produces: `RecoverySnapshot(document_path: Path | None, saved_at_utc: str, project_path: Path)`; `RecoveryStore(directory: Path, repository: ProjectRepository)` with `write(project, document_path, *, now=None) -> RecoverySnapshot`, `read() -> RecoverySnapshot | None`, `load_project(snapshot) -> InductorProject`, `clear() -> None`; the constants `RECOVERY_INDEX_FILENAME = "recovery-index.json"` and `RECOVERY_DOCUMENT_FILENAME = "recovery.inductor.json"`. On `ProjectSession`: constructor keyword `autosave_callback: Callable[[InductorProject, Path | None], None] | None = None`, `@Slot() flushAutosave()`, and the module constant `AUTOSAVE_DEBOUNCE_MS`.

**Three properties that make this safe, each with a test below:**

1. Autosave writes through `ProjectRepository.save`, so a snapshot is schema-v5 validated and non-finite values are refused. A snapshot that could not be loaded back is never written.
2. Autosave does **not** touch the user's `*.inductor.json` and does **not** clear `dirty`. The M7c `Generate` gate keeps refusing to run an unsaved project, because an autosave is a recovery aid, not a save.
3. An autosave failure is reported and logged, never raised. The previous snapshot stays on disk.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/adapters/persistence/test_recovery_store.py
from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from inductor_designer.adapters.persistence.project_repository import ProjectRepository
from inductor_designer.adapters.persistence.recovery_store import (
    RECOVERY_DOCUMENT_FILENAME,
    RECOVERY_INDEX_FILENAME,
    RecoveryStore,
)
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from tests.unit.domain.test_project import make_project

NOW = datetime(2026, 8, 18, 10, 15, 0, tzinfo=timezone.utc)


def _store(tmp_path: Path) -> RecoveryStore:
    return RecoveryStore(
        tmp_path / "recovery", ProjectRepository(SchemaRepository(Path("schemas")))
    )


def test_nothing_written_reads_as_no_snapshot(tmp_path: Path) -> None:
    assert _store(tmp_path).read() is None


def test_write_then_read_round_trips_the_project(tmp_path: Path) -> None:
    store = _store(tmp_path)
    document_path = tmp_path / "boost.inductor.json"
    project = replace(make_project(), description="unsaved edit")

    snapshot = store.write(project, document_path, now=NOW)

    assert snapshot.document_path == document_path
    assert snapshot.saved_at_utc == "2026-08-18T10:15:00+00:00"
    assert snapshot.project_path.name == RECOVERY_DOCUMENT_FILENAME
    reread = store.read()
    assert reread is not None
    assert store.load_project(reread).description == "unsaved edit"


def test_an_unsaved_project_records_no_document_path(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.write(make_project(), None, now=NOW)

    snapshot = store.read()
    assert snapshot is not None
    assert snapshot.document_path is None


def test_write_overwrites_the_previous_snapshot(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.write(replace(make_project(), description="old"), None, now=NOW)
    store.write(replace(make_project(), description="new"), None, now=NOW)

    snapshot = store.read()
    assert snapshot is not None
    assert store.load_project(snapshot).description == "new"


def test_a_non_finite_value_is_refused_and_leaves_the_old_snapshot(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    store.write(replace(make_project(), description="good"), None, now=NOW)
    broken = make_project()
    broken = replace(
        broken,
        operating_point=replace(broken.operating_point, frequency_hz=float("inf")),
    )

    with pytest.raises(ValueError):
        store.write(broken, None, now=NOW)

    snapshot = store.read()
    assert snapshot is not None
    assert store.load_project(snapshot).description == "good"


def test_a_corrupt_index_reads_as_no_snapshot(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.write(make_project(), None, now=NOW)
    (tmp_path / "recovery" / RECOVERY_INDEX_FILENAME).write_text(
        "not json", encoding="utf-8"
    )

    assert store.read() is None


def test_clear_removes_both_files(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.write(make_project(), None, now=NOW)

    store.clear()

    assert store.read() is None
    assert not (tmp_path / "recovery" / RECOVERY_DOCUMENT_FILENAME).exists()
    assert not (tmp_path / "recovery" / RECOVERY_INDEX_FILENAME).exists()


def test_the_index_records_the_document_path_as_written(tmp_path: Path) -> None:
    store = _store(tmp_path)
    document_path = tmp_path / "boost.inductor.json"
    store.write(make_project(), document_path, now=NOW)

    index = json.loads(
        (tmp_path / "recovery" / RECOVERY_INDEX_FILENAME).read_text(encoding="utf-8")
    )
    assert index["documentPath"] == str(document_path)
    assert index["savedAtUtc"] == "2026-08-18T10:15:00+00:00"
```

```python
# tests/ui/test_autosave.py
from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.domain.project import InductorProject  # noqa: E402
from inductor_designer.ui.project_session import ProjectSession  # noqa: E402
from tests.unit.domain.test_project import make_project  # noqa: E402

pytestmark = pytest.mark.ui


def _session(
    calls: list[tuple[InductorProject, Path | None]], **kwargs: object
) -> ProjectSession:
    QGuiApplication.instance() or QGuiApplication([])
    return ProjectSession(
        make_project(),
        autosave_callback=lambda project, path: calls.append((project, path)),
        **kwargs,  # type: ignore[arg-type]
    )


def test_an_edit_autosaves_the_edited_project() -> None:
    calls: list[tuple[InductorProject, Path | None]] = []
    session = _session(calls)
    session.apply(replace(session.project, description="edited"))

    session.flushAutosave()

    assert [project.description for project, _ in calls] == ["edited"]


def test_autosave_does_not_clear_dirty_so_generate_stays_gated() -> None:
    calls: list[tuple[InductorProject, Path | None]] = []
    session = _session(calls)
    session.apply(replace(session.project, description="edited"))

    session.flushAutosave()

    assert session.dirty is True


def test_autosave_never_writes_the_project_document(tmp_path: Path) -> None:
    document = tmp_path / "boost.inductor.json"
    document.write_text("{}", encoding="utf-8")
    calls: list[tuple[InductorProject, Path | None]] = []
    session = _session(calls, document_path=document)
    session.apply(replace(session.project, description="edited"))

    session.flushAutosave()

    assert document.read_text(encoding="utf-8") == "{}"
    assert calls[0][1] == document


def test_undo_autosaves_the_restored_project() -> None:
    calls: list[tuple[InductorProject, Path | None]] = []
    session = _session(calls)
    session.apply(replace(session.project, description="edited"))
    session.flushAutosave()
    calls.clear()

    session.undo()
    session.flushAutosave()

    assert [project.description for project, _ in calls] == [
        make_project().description
    ]


def test_an_autosave_failure_is_reported_and_does_not_raise() -> None:
    QGuiApplication.instance() or QGuiApplication([])

    def explode(project: InductorProject, path: Path | None) -> None:
        raise OSError("disk full")

    session = ProjectSession(make_project(), autosave_callback=explode)
    session.apply(replace(session.project, description="edited"))

    session.flushAutosave()

    assert "autosave" in session.statusMessage.casefold()
    assert session.project.description == "edited"


def test_flush_without_a_pending_edit_writes_nothing() -> None:
    calls: list[tuple[InductorProject, Path | None]] = []
    session = _session(calls)

    session.flushAutosave()

    assert calls == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/adapters/persistence/test_recovery_store.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'inductor_designer.adapters.persistence.recovery_store'`

- [ ] **Step 3: Write the implementation**

```python
# src/inductor_designer/adapters/persistence/recovery_store.py
"""The autosaved recovery snapshot: one project, plus where it came from.

The snapshot document is written by `ProjectRepository`, so it inherits
schema-v5 validation, the non-finite refusal, and the atomic temp-file replace.
A snapshot that cannot be loaded back is therefore never written.

The index is written after the document, so a half-written pair is detected as
"no snapshot" rather than restored as a project.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from inductor_designer.adapters.persistence.project_repository import ProjectRepository
from inductor_designer.domain.project import InductorProject

RECOVERY_INDEX_FILENAME = "recovery-index.json"
RECOVERY_DOCUMENT_FILENAME = "recovery.inductor.json"


@dataclass(frozen=True, slots=True)
class RecoverySnapshot:
    """One autosaved project: where it belongs, when it was taken, where it is."""

    document_path: Path | None
    saved_at_utc: str
    project_path: Path


class RecoveryStore:
    def __init__(self, directory: Path, repository: ProjectRepository) -> None:
        self._directory = directory
        self._repository = repository

    @property
    def index_path(self) -> Path:
        return self._directory / RECOVERY_INDEX_FILENAME

    @property
    def document_path(self) -> Path:
        return self._directory / RECOVERY_DOCUMENT_FILENAME

    def write(
        self,
        project: InductorProject,
        document_path: Path | None,
        *,
        now: datetime | None = None,
    ) -> RecoverySnapshot:
        """Overwrite the snapshot. Raises rather than writing an invalid one."""
        self._directory.mkdir(parents=True, exist_ok=True)
        moment = (datetime.now(timezone.utc) if now is None else now).astimezone(
            timezone.utc
        )
        self._repository.save(project, self.document_path)
        self.index_path.write_text(
            json.dumps(
                {
                    "documentPath": None if document_path is None else str(document_path),
                    "savedAtUtc": moment.isoformat(),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return RecoverySnapshot(
            document_path=document_path,
            saved_at_utc=moment.isoformat(),
            project_path=self.document_path,
        )

    def read(self) -> RecoverySnapshot | None:
        """The snapshot, or None when there is nothing trustworthy to offer."""
        if not self.index_path.is_file() or not self.document_path.is_file():
            return None
        try:
            index = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(index, dict):
            return None
        raw_path = index.get("documentPath")
        saved_at = index.get("savedAtUtc")
        if not isinstance(saved_at, str):
            return None
        return RecoverySnapshot(
            document_path=Path(raw_path) if isinstance(raw_path, str) else None,
            saved_at_utc=saved_at,
            project_path=self.document_path,
        )

    def load_project(self, snapshot: RecoverySnapshot) -> InductorProject:
        return self._repository.load(snapshot.project_path)

    def clear(self) -> None:
        self.index_path.unlink(missing_ok=True)
        self.document_path.unlink(missing_ok=True)
```

In `src/inductor_designer/ui/project_session.py`, add the constant, the timer and the flush:

```python
# Long enough that dragging a numeric field does not write a file per frame,
# short enough that a crash loses at most this much work.
AUTOSAVE_DEBOUNCE_MS = 2000
```

In `__init__`, accept `autosave_callback: Callable[[InductorProject, Path | None], None] | None = None`, store it, and build the timer:

```python
        self._autosave_callback = autosave_callback
        self._autosave_pending = False
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(AUTOSAVE_DEBOUNCE_MS)
        self._autosave_timer.timeout.connect(self.flushAutosave)
```

Add the scheduling call at the end of `apply`, `undo` and `redo`:

```python
    def _schedule_autosave(self) -> None:
        if self._autosave_callback is None:
            return
        self._autosave_pending = True
        self._autosave_timer.start()

    @Slot()
    def flushAutosave(self) -> None:
        """Write the pending snapshot now. Never raises: a failed autosave must
        not take the edit or the session with it."""
        self._autosave_timer.stop()
        if not self._autosave_pending or self._autosave_callback is None:
            return
        self._autosave_pending = False
        try:
            self._autosave_callback(self.project, self._document_path)
        except Exception as error:  # noqa: BLE001 - autosave must never wedge the UI
            logging.getLogger(LOGGER_NAME).warning("Autosave failed: %s", error)
            self.set_status(f"Unable to autosave a recovery copy: {error}")
```

In `saveProject` and `saveProjectAs`, after the successful write, drop the pending autosave and clear the snapshot — what is on disk needs no recovery:

```python
        self._autosave_pending = False
        self._autosave_timer.stop()
        if self._recovery_cleanup is not None:
            self._recovery_cleanup()
```

where `_recovery_cleanup: Callable[[], None] | None` is a second optional constructor keyword bound in `main.py` to `store.clear`.

In `src/inductor_designer/ui/main.py`, next to the existing `save_project` closure:

```python
    from inductor_designer.adapters.persistence.recovery_store import RecoveryStore
    from inductor_designer.adapters.system.environment import recovery_directory

    recovery_store = RecoveryStore(recovery_directory(), project_repository)

    def autosave_project(
        updated_project: InductorProject, document_path: Path | None
    ) -> None:
        recovery_store.write(updated_project, document_path)
```

and pass `autosave_callback=autosave_project, recovery_cleanup=recovery_store.clear` when the session is built.

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/adapters/persistence -q`
Expected: PASS

Run: `set QT_QPA_PLATFORM=offscreen && set QSG_RHI_BACKEND=software && .venv/Scripts/python.exe -m pytest tests/ui -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/adapters/persistence/recovery_store.py src/inductor_designer/ui tests/unit/adapters/persistence tests/ui/test_autosave.py
git commit -m "feat(ui): autosave a validated recovery snapshot outside the project directory"
```

---

### Task 6: Crash recovery at startup

**Files:**
- Create: `src/inductor_designer/ui/recovery_controller.py`
- Modify: `src/inductor_designer/ui/project_session.py` (recovered-project entry point)
- Modify: `src/inductor_designer/ui/main.py` (build and expose the controller)
- Modify: `src/inductor_designer/ui/qml/Main.qml` (the recovery dialog)
- Test: `tests/ui/test_crash_recovery.py`

**Interfaces:**
- Consumes: `RecoveryStore`, `RecoverySnapshot` from Task 5; `ProjectSession`.
- Produces: `RecoveryController(store: RecoveryStore, session: ProjectSession, parent=None)` with `available: Property(bool)`, `summary: Property(str)`, `@Slot(result=bool) recover()`, `@Slot(result=bool) discard()`, and the signal `offerChanged`. On `ProjectSession`: `applyRecovered(project: InductorProject) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/ui/test_crash_recovery.py
"""A snapshot newer than the document is offered; recovery never overwrites disk."""

from __future__ import annotations

import os
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.adapters.persistence.project_repository import (  # noqa: E402
    ProjectRepository,
)
from inductor_designer.adapters.persistence.recovery_store import (  # noqa: E402
    RecoveryStore,
)
from inductor_designer.adapters.persistence.schema_repository import (  # noqa: E402
    SchemaRepository,
)
from inductor_designer.ui.project_session import ProjectSession  # noqa: E402
from inductor_designer.ui.recovery_controller import RecoveryController  # noqa: E402
from tests.unit.domain.test_project import make_project  # noqa: E402

pytestmark = pytest.mark.ui

LATER = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)


def _store(tmp_path: Path) -> RecoveryStore:
    return RecoveryStore(
        tmp_path / "recovery", ProjectRepository(SchemaRepository(Path("schemas")))
    )


def _saved_document(tmp_path: Path) -> Path:
    path = tmp_path / "boost.inductor.json"
    ProjectRepository(SchemaRepository(Path("schemas"))).save(make_project(), path)
    return path


def test_no_snapshot_means_no_offer(tmp_path: Path) -> None:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())
    controller = RecoveryController(_store(tmp_path), session)

    assert controller.available is False
    assert controller.recover() is False


def test_a_newer_snapshot_is_offered_and_summarised(tmp_path: Path) -> None:
    QGuiApplication.instance() or QGuiApplication([])
    document = _saved_document(tmp_path)
    store = _store(tmp_path)
    store.write(replace(make_project(), description="unsaved"), document, now=LATER)
    session = ProjectSession(make_project(), document_path=document)
    controller = RecoveryController(store, session)

    assert controller.available is True
    assert "2026-08-18" in controller.summary


def test_recover_loads_the_snapshot_dirty_without_touching_disk(
    tmp_path: Path,
) -> None:
    QGuiApplication.instance() or QGuiApplication([])
    document = _saved_document(tmp_path)
    on_disk = document.read_text(encoding="utf-8")
    store = _store(tmp_path)
    store.write(replace(make_project(), description="unsaved"), document, now=LATER)
    session = ProjectSession(make_project(), document_path=document)
    controller = RecoveryController(store, session)

    assert controller.recover() is True

    assert session.project.description == "unsaved"
    assert session.dirty is True
    assert document.read_text(encoding="utf-8") == on_disk
    assert controller.available is False


def test_discard_clears_the_snapshot_and_leaves_the_session_alone(
    tmp_path: Path,
) -> None:
    QGuiApplication.instance() or QGuiApplication([])
    document = _saved_document(tmp_path)
    store = _store(tmp_path)
    store.write(replace(make_project(), description="unsaved"), document, now=LATER)
    session = ProjectSession(make_project(), document_path=document)
    controller = RecoveryController(store, session)

    assert controller.discard() is True

    assert store.read() is None
    assert session.project.description == make_project().description
    assert session.dirty is False
    assert controller.available is False


def test_a_snapshot_older_than_the_document_is_not_offered(tmp_path: Path) -> None:
    QGuiApplication.instance() or QGuiApplication([])
    document = _saved_document(tmp_path)
    store = _store(tmp_path)
    store.write(
        replace(make_project(), description="stale"),
        document,
        now=datetime.fromtimestamp(document.stat().st_mtime, tz=timezone.utc)
        - timedelta(minutes=5),
    )
    session = ProjectSession(make_project(), document_path=document)

    assert RecoveryController(store, session).available is False


def test_a_snapshot_for_an_unsaved_project_is_always_offered(tmp_path: Path) -> None:
    QGuiApplication.instance() or QGuiApplication([])
    store = _store(tmp_path)
    store.write(replace(make_project(), description="unsaved"), None, now=LATER)
    session = ProjectSession(make_project())

    assert RecoveryController(store, session).available is True


def test_an_unreadable_snapshot_document_is_not_offered(tmp_path: Path) -> None:
    QGuiApplication.instance() or QGuiApplication([])
    store = _store(tmp_path)
    store.write(replace(make_project(), description="unsaved"), None, now=LATER)
    store.document_path.write_text("{}", encoding="utf-8")
    session = ProjectSession(make_project())
    controller = RecoveryController(store, session)

    assert controller.recover() is False
    assert "recover" in session.statusMessage.casefold()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `set QT_QPA_PLATFORM=offscreen && .venv/Scripts/python.exe -m pytest tests/ui/test_crash_recovery.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'inductor_designer.ui.recovery_controller'`

- [ ] **Step 3: Write the implementation**

```python
# src/inductor_designer/ui/recovery_controller.py
"""Offer the last autosaved snapshot after an abnormal exit.

Recovery loads the snapshot into the running session and leaves it dirty: the
recovered project is explicitly *not* on disk, so the user still has to save it,
and the M7c Generate gate still refuses to run it until they do. Nothing here
writes the user's project document.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from PySide6.QtCore import Property, QObject, Signal, Slot

from inductor_designer.adapters.system.app_logging import LOGGER_NAME

if TYPE_CHECKING:
    from inductor_designer.adapters.persistence.recovery_store import (
        RecoverySnapshot,
        RecoveryStore,
    )
    from inductor_designer.ui.project_session import ProjectSession


class RecoveryController(QObject):
    offerChanged = Signal()

    def __init__(
        self,
        store: RecoveryStore,
        session: ProjectSession,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._session = session
        self._snapshot = self._offerable(store.read())

    def _offerable(self, snapshot: RecoverySnapshot | None) -> RecoverySnapshot | None:
        """Only a snapshot that is newer than what is already on disk.

        A snapshot older than the saved document describes work the user
        already saved; offering it would invite them to go backwards.
        """
        if snapshot is None:
            return None
        document_path = snapshot.document_path
        if document_path is None or not document_path.is_file():
            return snapshot
        try:
            saved_at = datetime.fromisoformat(snapshot.saved_at_utc)
        except ValueError:
            return None
        document_time = datetime.fromtimestamp(
            document_path.stat().st_mtime, tz=timezone.utc
        )
        return snapshot if saved_at > document_time else None

    def _get_available(self) -> bool:
        return self._snapshot is not None

    available = Property(bool, _get_available, notify=offerChanged)

    def _get_summary(self) -> str:
        snapshot = self._snapshot
        if snapshot is None:
            return ""
        target = (
            "an unsaved project"
            if snapshot.document_path is None
            else snapshot.document_path.name
        )
        return (
            f"Unsaved changes to {target} were autosaved at "
            f"{snapshot.saved_at_utc}. Recover them, or discard them and keep "
            "the version on disk."
        )

    summary = Property(str, _get_summary, notify=offerChanged)

    @Slot(result=bool)
    def recover(self) -> bool:
        snapshot = self._snapshot
        if snapshot is None:
            return False
        try:
            project = self._store.load_project(snapshot)
        except Exception as error:  # noqa: BLE001 - a bad snapshot must not crash
            logging.getLogger(LOGGER_NAME).warning(
                "Recovery snapshot could not be loaded: %s", error
            )
            self._session.set_status(
                f"Unable to recover the autosaved changes: {error}"
            )
            self._snapshot = None
            self.offerChanged.emit()
            return False
        self._session.applyRecovered(project)
        logging.getLogger(LOGGER_NAME).info("Recovered autosaved project changes.")
        self._snapshot = None
        self.offerChanged.emit()
        return True

    @Slot(result=bool)
    def discard(self) -> bool:
        self._store.clear()
        self._snapshot = None
        self.offerChanged.emit()
        return True
```

In `ProjectSession`, add the recovered-project entry point:

```python
    def applyRecovered(self, project: InductorProject) -> None:
        """Adopt a recovered snapshot as the current project.

        Deliberately not `apply`: there is no earlier in-session edit to undo
        back to, and the recovered project is not on disk, so it stays dirty.
        """
        self._undo.clear()
        self._redo.clear()
        self._provider.replace(project)
        self._refresh_dirty()
        self.undoStackChanged.emit()
        self.projectChanged.emit()
        self.set_status("Recovered unsaved changes")
```

In `main.py`, build `RecoveryController(recovery_store, session)` after the session exists, keep it in a local name (the `AppInfoController` comment explains why), and pass it into `create_engine` as a new `recovery_controller` parameter exposed as the `recoveryController` context property.

In `Main.qml`, add a dialog that opens once on completion when the offer exists:

```qml
    Component.onCompleted: {
        if (typeof recoveryController !== "undefined"
            && recoveryController !== null
            && recoveryController.available) {
            recoveryDialog.open()
        }
    }

    Dialog {
        id: recoveryDialog
        objectName: "recoveryDialog"
        title: qsTr("Recover unsaved changes?")
        modal: true
        anchors.centerIn: Overlay.overlay
        closePolicy: Popup.NoAutoClose

        contentItem: Label {
            objectName: "recoveryDialogMessage"
            text: recoveryController === null ? "" : recoveryController.summary
            wrapMode: Text.WordWrap
        }

        footer: DialogButtonBox {
            Button {
                objectName: "recoverButton"
                text: qsTr("Recover")
                onClicked: {
                    recoveryController.recover()
                    recoveryDialog.close()
                }
            }
            Button {
                objectName: "discardRecoveryButton"
                text: qsTr("Discard")
                onClicked: {
                    recoveryController.discard()
                    recoveryDialog.close()
                }
            }
        }
    }
```

- [ ] **Step 4: Run the tests**

Run: `set QT_QPA_PLATFORM=offscreen && set QSG_RHI_BACKEND=software && .venv/Scripts/python.exe -m pytest tests/ui -q`
Expected: PASS, including `tests/ui/test_qml_smoke.py` and `tests/ui/test_main_wiring.py`

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/ui tests/ui/test_crash_recovery.py
git commit -m "feat(ui): offer the autosaved snapshot after an abnormal exit"
```

---

### Task 7: Interrupted-run recovery that never re-solves in place

**Files:**
- Modify: `src/inductor_designer/simulation/run_contracts.py:27-33` (`RunStatus`)
- Create: `src/inductor_designer/application/services/run_recovery.py`
- Modify: `src/inductor_designer/ui/review_controller.py:197-211,277-306`
- Modify: `src/inductor_designer/ui/qml/ReviewPage.qml`
- Modify: `src/inductor_designer/ui/main.py` (reconcile at startup), `src/inductor_designer/ui/project_session.py` (reconcile on Open)
- Test: `tests/unit/application/test_run_recovery.py`
- Test: `tests/ui/test_review_interrupted_runs.py`

**Interfaces:**
- Consumes: `RunStatus`, `RUNS_DIRECTORY_NAME`, `MANIFEST_FILENAME` from `application/services/run_directory.py`.
- Produces: `RunStatus.INTERRUPTED = "interrupted"`; in `run_recovery.py`: `INTERRUPTED_DIAGNOSTIC = "run.interrupted_before_completion"`, `UNSOLVED_ARTIFACT_DIAGNOSTIC = "run.artifact_saved_but_unsolved"`, `UnfinishedRun(run_id: str, backend: str, mode: str | None, directory: Path, manifest_path: Path, started_utc: str | None, reconciled: bool)`, `find_unfinished_runs(project_document_path: Path) -> tuple[UnfinishedRun, ...]`, `reconcile_unfinished_runs(project_document_path: Path, *, now: datetime | None = None) -> tuple[UnfinishedRun, ...]`.

**The hazard this must not repeat, observed live on 2026-08-18:** the Maxwell solve stage sequence saves the project *before* it analyses (`SOLVE_STAGE_NAMES` in `application/ports/maxwell_exporter.py` puts `save` before `analyze`). A killed process therefore leaves a saved-but-unsolved `*.aedt` in the run directory *and* a `run-manifest.json` still reading `"status": "running"`. Re-solving that directory failed with AEDT's `Engine Detected Error` on a missing `.adp` file. Recovery therefore **reconciles the record and offers a new run; it never resumes, re-opens, or re-solves an existing run directory.** There is deliberately no "Resume" control anywhere in this task.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/application/test_run_recovery.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from inductor_designer.application.services.run_recovery import (
    INTERRUPTED_DIAGNOSTIC,
    UNSOLVED_ARTIFACT_DIAGNOSTIC,
    find_unfinished_runs,
    reconcile_unfinished_runs,
)
from inductor_designer.simulation.run_contracts import RunStatus

NOW = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)


def _project(tmp_path: Path) -> Path:
    path = tmp_path / "boost.inductor.json"
    path.write_text("{}", encoding="utf-8")
    return path


def _run(tmp_path: Path, run_id: str, backend: str, status: str | None) -> Path:
    directory = tmp_path / "runs" / f"{run_id}-{backend}"
    (directory / "results").mkdir(parents=True)
    if status is not None:
        (directory / "run-manifest.json").write_text(
            json.dumps(
                {
                    "runId": run_id,
                    "backend": backend,
                    "mode": "generate-and-solve",
                    "status": status,
                    "startedUtc": "2026-08-18T10:15:00+00:00",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    return directory


def test_no_runs_directory_finds_nothing(tmp_path: Path) -> None:
    assert find_unfinished_runs(_project(tmp_path)) == ()


def test_a_succeeded_run_is_not_unfinished(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _run(tmp_path, "20260818-101500", "maxwell-3d", RunStatus.SUCCEEDED.value)

    assert find_unfinished_runs(project) == ()


def test_a_running_manifest_is_unfinished(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _run(tmp_path, "20260818-101500", "maxwell-3d", RunStatus.RUNNING.value)

    found = find_unfinished_runs(project)

    assert [run.run_id for run in found] == ["20260818-101500"]
    assert found[0].backend == "maxwell-3d"
    assert found[0].reconciled is False


def test_a_run_directory_without_a_manifest_is_unfinished(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _run(tmp_path, "20260818-101500", "femm", None)

    found = find_unfinished_runs(project)

    assert [run.backend for run in found] == ["femm"]
    assert found[0].started_utc is None


def test_reconcile_rewrites_running_to_interrupted(tmp_path: Path) -> None:
    project = _project(tmp_path)
    directory = _run(tmp_path, "20260818-101500", "maxwell-3d", RunStatus.RUNNING.value)

    reconcile_unfinished_runs(project, now=NOW)

    document = json.loads(
        (directory / "run-manifest.json").read_text(encoding="utf-8")
    )
    assert document["status"] == RunStatus.INTERRUPTED.value
    assert document["startedUtc"] == "2026-08-18T10:15:00+00:00"
    assert document["reconciledUtc"] == "2026-08-18T12:00:00+00:00"
    assert document["results"] is None
    assert any(
        line.startswith(INTERRUPTED_DIAGNOSTIC) for line in document["diagnostics"]
    )


def test_a_saved_but_unsolved_solver_file_is_named_and_never_reused(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    directory = _run(tmp_path, "20260818-101500", "maxwell-3d", RunStatus.RUNNING.value)
    (directory / "Inductor3D.aedt").write_text("saved before the solve", encoding="utf-8")

    reconcile_unfinished_runs(project, now=NOW)

    document = json.loads(
        (directory / "run-manifest.json").read_text(encoding="utf-8")
    )
    advice = next(
        line
        for line in document["diagnostics"]
        if line.startswith(UNSOLVED_ARTIFACT_DIAGNOSTIC)
    )
    assert "new run" in advice.casefold()
    assert document["artifacts"] == [
        {"kind": "unsolved-solver-project", "path": "Inductor3D.aedt"}
    ]
    # The evidence is preserved, not deleted: it is the user's file.
    assert (directory / "Inductor3D.aedt").is_file()


def test_reconcile_is_idempotent(tmp_path: Path) -> None:
    project = _project(tmp_path)
    directory = _run(tmp_path, "20260818-101500", "femm", RunStatus.RUNNING.value)

    reconcile_unfinished_runs(project, now=NOW)
    first = (directory / "run-manifest.json").read_text(encoding="utf-8")
    reconcile_unfinished_runs(
        project, now=datetime(2026, 8, 18, 13, 0, 0, tzinfo=timezone.utc)
    )

    assert (directory / "run-manifest.json").read_text(encoding="utf-8") == first


def test_an_interrupted_run_stays_visible_after_reconciliation(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _run(tmp_path, "20260818-101500", "femm", RunStatus.RUNNING.value)

    reconcile_unfinished_runs(project, now=NOW)
    found = find_unfinished_runs(project)

    assert [run.reconciled for run in found] == [True]


def test_a_cancelled_run_is_not_unfinished(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _run(tmp_path, "20260818-101500", "femm", RunStatus.CANCELLED.value)

    assert find_unfinished_runs(project) == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/application/test_run_recovery.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'inductor_designer.application.services.run_recovery'`

- [ ] **Step 3: Write the implementation**

Add to `RunStatus` in `run_contracts.py`, immediately after `CANCELLED`:

```python
    # A run whose process died before it could write its own outcome. Set only
    # by run recovery, never by an adapter.
    INTERRUPTED = "interrupted"
```

```python
# src/inductor_designer/application/services/run_recovery.py
"""Reconcile the runs a killed process left behind (ADR 0007, roadmap 8).

`start_project_run` writes a `"status": "running"` marker before it dispatches
to an adapter and overwrites it with the real manifest when the run ends. A
document still reading `running` therefore means the process died mid-run, and
the only truthful thing to say about it is that it was interrupted and produced
no result.

Recovery never re-solves. The Maxwell solve sequence saves the project before
it analyses, so an interrupted run leaves a saved-but-unsolved `*.aedt` behind;
re-solving such a directory was observed on 2026-08-18 to fail with AEDT's
`Engine Detected Error` on a missing `.adp`. The reconciled record therefore
names the unsolved artifact and tells the user to start a new run, which gets
its own directory. Nothing here deletes a solver file: it is the user's output.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from inductor_designer.application.services.run_directory import (
    MANIFEST_FILENAME,
    RUNS_DIRECTORY_NAME,
)
from inductor_designer.simulation.run_contracts import RunStatus

INTERRUPTED_DIAGNOSTIC = "run.interrupted_before_completion"
UNSOLVED_ARTIFACT_DIAGNOSTIC = "run.artifact_saved_but_unsolved"

UNSOLVED_ARTIFACT_KIND = "unsolved-solver-project"
_SOLVER_FILE_SUFFIXES = (".aedt", ".fem")
_UNFINISHED_STATUSES = frozenset({RunStatus.RUNNING.value, RunStatus.INTERRUPTED.value})

_INTERRUPTED_MESSAGE = (
    "The application or the solver stopped before this run finished. No "
    "result was produced, and no part of this run may be read as a result."
)
_UNSOLVED_ARTIFACT_MESSAGE = (
    "A solver project was saved before the analysis ran, so it holds geometry "
    "and setup but no solution. Start a new run, which gets its own "
    "directory; solving this directory again fails on its missing solver data."
)


@dataclass(frozen=True, slots=True)
class UnfinishedRun:
    """One run directory that holds no outcome."""

    run_id: str
    backend: str
    mode: str | None
    directory: Path
    manifest_path: Path
    started_utc: str | None
    reconciled: bool


def _runs_root(project_document_path: Path) -> Path:
    return project_document_path.resolve().parent / RUNS_DIRECTORY_NAME


def _read_document(path: Path) -> dict[str, object] | None:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _identity_from_directory(directory: Path) -> tuple[str, str]:
    """`<run-id>-<backend>` split from the right, because a run id has hyphens."""
    name = directory.name
    for backend in ("maxwell-3d", "maxwell-2d", "femm"):
        suffix = f"-{backend}"
        if name.endswith(suffix):
            return name[: -len(suffix)], backend
    return name, "unknown"


def find_unfinished_runs(project_document_path: Path) -> tuple[UnfinishedRun, ...]:
    """Every run directory that holds no outcome, oldest first.

    A directory with no manifest at all counts: the marker is written right
    after the directory is created, so its absence is the same evidence as a
    `running` status, and silently ignoring it would hide a lost run.
    """
    runs_root = _runs_root(project_document_path)
    if not runs_root.is_dir():
        return ()
    unfinished: list[UnfinishedRun] = []
    for directory in sorted(entry for entry in runs_root.iterdir() if entry.is_dir()):
        manifest_path = directory / MANIFEST_FILENAME
        document = _read_document(manifest_path) if manifest_path.is_file() else None
        if document is None:
            run_id, backend = _identity_from_directory(directory)
            unfinished.append(
                UnfinishedRun(
                    run_id=run_id,
                    backend=backend,
                    mode=None,
                    directory=directory,
                    manifest_path=manifest_path,
                    started_utc=None,
                    reconciled=False,
                )
            )
            continue
        status = document.get("status")
        if status not in _UNFINISHED_STATUSES:
            continue
        run_id_value = document.get("runId")
        backend_value = document.get("backend")
        mode_value = document.get("mode")
        started_value = document.get("startedUtc")
        fallback_id, fallback_backend = _identity_from_directory(directory)
        unfinished.append(
            UnfinishedRun(
                run_id=run_id_value if isinstance(run_id_value, str) else fallback_id,
                backend=(
                    backend_value
                    if isinstance(backend_value, str)
                    else fallback_backend
                ),
                mode=mode_value if isinstance(mode_value, str) else None,
                directory=directory,
                manifest_path=manifest_path,
                started_utc=started_value if isinstance(started_value, str) else None,
                reconciled=status == RunStatus.INTERRUPTED.value,
            )
        )
    return tuple(unfinished)


def _unsolved_artifacts(directory: Path) -> tuple[dict[str, str], ...]:
    return tuple(
        {"kind": UNSOLVED_ARTIFACT_KIND, "path": path.name}
        for path in sorted(directory.iterdir())
        if path.is_file() and path.suffix.casefold() in _SOLVER_FILE_SUFFIXES
    )


def reconcile_unfinished_runs(
    project_document_path: Path, *, now: datetime | None = None
) -> tuple[UnfinishedRun, ...]:
    """Rewrite every unreconciled record as interrupted. Idempotent.

    Returns every unfinished run, reconciled or already reconciled, so a caller
    can display them without a second scan.
    """
    moment = (datetime.now(timezone.utc) if now is None else now).astimezone(
        timezone.utc
    )
    for run in find_unfinished_runs(project_document_path):
        if run.reconciled:
            continue
        artifacts = _unsolved_artifacts(run.directory)
        diagnostics = [f"{INTERRUPTED_DIAGNOSTIC}: {_INTERRUPTED_MESSAGE}"]
        if artifacts:
            diagnostics.append(
                f"{UNSOLVED_ARTIFACT_DIAGNOSTIC}: {_UNSOLVED_ARTIFACT_MESSAGE}"
            )
        document = {
            "runId": run.run_id,
            "backend": run.backend,
            "mode": run.mode,
            "status": RunStatus.INTERRUPTED.value,
            "startedUtc": run.started_utc,
            "reconciledUtc": moment.isoformat(),
            "diagnostics": diagnostics,
            "artifacts": [dict(artifact) for artifact in artifacts],
            # Never a result: an interrupted run has none, and an absent key
            # would let a reader assume one was simply not exported.
            "results": None,
        }
        run.manifest_path.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return find_unfinished_runs(project_document_path)
```

In `review_controller.py`, extend `_run_rows` and add the per-run open slot:

```python
        for run in self._interrupted_runs():
            rows.append(
                {
                    "label": "Interrupted run",
                    "text": (
                        f"{run.run_id} ({run.backend}): no result. Start a new "
                        "run; this directory cannot be solved again."
                    ),
                }
            )
```

```python
    def _interrupted_runs(self) -> tuple[UnfinishedRun, ...]:
        document_path = self._session.document_path
        if document_path is None:
            return ()
        return find_unfinished_runs(document_path)

    @Slot(str, result=bool)
    def openRunFolderById(self, run_id: str) -> bool:
        for run in self._interrupted_runs():
            if run.run_id == run_id:
                return self._open(run.directory, "run folder")
        return False
```

Add an `interruptedRuns` `Property(list)` of `{"runId", "backend", "startedUtc"}` dictionaries so `ReviewPage.qml` can render one `Open run folder` button per interrupted run beside the existing run buttons.

Call `reconcile_unfinished_runs(document_path)` from exactly two places, both guarded with `contextlib.suppress(OSError)` because a reconciliation failure must never block opening a project: `main.py` at startup after the session exists, and `ProjectSession.openProject` after the new document path is adopted.

- [ ] **Step 4: Write the UI test**

```python
# tests/ui/test_review_interrupted_runs.py
"""The Review screen must name an interrupted run and never offer to resume it."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.simulation.run_contracts import RunStatus  # noqa: E402

pytestmark = pytest.mark.ui


def _interrupted_run(project_document_path: Path) -> Path:
    directory = (
        project_document_path.parent / "runs" / "20260818-101500-maxwell-3d"
    )
    (directory / "results").mkdir(parents=True)
    (directory / "run-manifest.json").write_text(
        json.dumps(
            {
                "runId": "20260818-101500",
                "backend": "maxwell-3d",
                "mode": "generate-and-solve",
                "status": RunStatus.RUNNING.value,
                "startedUtc": "2026-08-18T10:15:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    return directory


def test_an_interrupted_run_appears_in_the_run_section(tmp_path: Path) -> None:
    QGuiApplication.instance() or QGuiApplication([])
    from tests.ui.test_review_controller import review_controller_environment

    env = review_controller_environment(tmp_path)
    _interrupted_run(env.document_path)
    env.controller.refresh()

    run_section = next(
        section
        for section in env.controller.sections
        if section["title"] == "Run request"
    )
    texts = [row["text"] for row in run_section["rows"]]
    assert any("20260818-101500" in text for text in texts)
    assert any("cannot be solved again" in text for text in texts)
    assert not any("resume" in text.casefold() for text in texts)


def test_open_run_folder_by_id_reaches_the_path_opener(tmp_path: Path) -> None:
    QGuiApplication.instance() or QGuiApplication([])
    from tests.ui.test_review_controller import review_controller_environment

    env = review_controller_environment(tmp_path)
    directory = _interrupted_run(env.document_path)
    env.controller.refresh()

    assert env.controller.openRunFolderById("20260818-101500") is True
    assert env.opener.opened == [directory]


def test_an_unknown_run_id_opens_nothing(tmp_path: Path) -> None:
    QGuiApplication.instance() or QGuiApplication([])
    from tests.ui.test_review_controller import review_controller_environment

    env = review_controller_environment(tmp_path)
    env.controller.refresh()

    assert env.controller.openRunFolderById("19700101-000000") is False
    assert env.opener.opened == []
```

If `tests/ui/test_review_controller.py` has no reusable `review_controller_environment(tmp_path)` returning `controller`, `document_path` and a recording `opener`, extract one from its existing setup in this step and use it from both files rather than duplicating the wiring.

- [ ] **Step 5: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/application/test_run_recovery.py tests/unit/simulation/test_run_contracts.py -q`
Expected: PASS

Run: `set QT_QPA_PLATFORM=offscreen && set QSG_RHI_BACKEND=software && .venv/Scripts/python.exe -m pytest tests/ui tests/unit tests/integration -q`
Expected: PASS. The golden manifests are unchanged: adding an enum member changes no serialized value.

- [ ] **Step 6: Commit**

```bash
git add src/inductor_designer/simulation/run_contracts.py src/inductor_designer/application/services/run_recovery.py src/inductor_designer/ui tests
git commit -m "feat(runs): reconcile an interrupted run as interrupted and refuse to re-solve it"
```

---

### Task 8: The redacted diagnostic bundle

**Files:**
- Create: `src/inductor_designer/application/services/diagnostic_bundle.py`
- Create: `src/inductor_designer/adapters/system/diagnostic_archive.py`
- Create: `src/inductor_designer/ui/diagnostics_controller.py`
- Modify: `src/inductor_designer/ui/qml/Main.qml` (Help menu item and the save dialog)
- Modify: `src/inductor_designer/ui/main.py` (build and expose the controller)
- Test: `tests/unit/application/test_diagnostic_bundle.py`
- Test: `tests/unit/adapters/system/test_diagnostic_archive.py`
- Test: `tests/ui/test_diagnostics_controller.py`

**Interfaces:**
- Consumes: `redact_text`, `RedactionContext` (Task 1); `log_directory()`, `environment_redaction_context()` (Task 2); `RUNS_DIRECTORY_NAME`, `MANIFEST_FILENAME` (existing); `APP_LOG_FILENAME` (Task 2).
- Produces: in `diagnostic_bundle.py`: `BUNDLE_CONTENTS_FILENAME = "bundle-contents.json"`, `BundleSource(name: str, text: str)`, `BundleEntry(name: str, text: str)`, `build_bundle_entries(sources, context, *, application_version, created_utc) -> tuple[BundleEntry, ...]`. In `diagnostic_archive.py`: `BUNDLE_SUFFIX = ".diagnostics.zip"`, `collect_bundle_sources(project_document_path: Path | None, log_path: Path | None) -> tuple[BundleSource, ...]`, `write_diagnostic_archive(path: Path, entries: Sequence[BundleEntry]) -> Path`. On `DiagnosticsController`: `@Slot(QUrl, result=bool) saveBundle(target)`, `message: Property(str)`, `suggestedFileName: Property(str)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/application/test_diagnostic_bundle.py
"""Every byte and every name in a bundle passes through redaction, in one loop."""

from __future__ import annotations

import json

from inductor_designer.application.services.diagnostic_bundle import (
    BUNDLE_CONTENTS_FILENAME,
    BundleSource,
    build_bundle_entries,
)
from inductor_designer.application.services.redaction import (
    REDACTED_EMAIL,
    REDACTED_PATH,
    RedactionContext,
)

CONTEXT = RedactionContext(user_names=("jane.doe",), host_names=("BRUSA-WS42",))


def _entries(*sources: BundleSource) -> dict[str, str]:
    built = build_bundle_entries(
        sources,
        CONTEXT,
        application_version="0.9.0",
        created_utc="2026-08-18T12:00:00+00:00",
    )
    return {entry.name: entry.text for entry in built}


def test_entry_text_is_redacted() -> None:
    entries = _entries(
        BundleSource(name="logs/app.log", text=r"saved C:\Users\jane.doe\b.aedt")
    )
    assert "jane.doe" not in entries["logs/app.log"]
    assert f"{REDACTED_PATH}.aedt" in entries["logs/app.log"]


def test_entry_name_is_redacted_too() -> None:
    entries = _entries(BundleSource(name="runs/jane.doe-run/x.json", text="ok"))
    assert not any("jane.doe" in name for name in entries)


def test_the_contents_index_lists_every_entry() -> None:
    entries = _entries(
        BundleSource(name="logs/app.log", text="a"),
        BundleSource(name="runs/r/run-manifest.json", text="b"),
    )
    index = json.loads(entries[BUNDLE_CONTENTS_FILENAME])
    assert index["applicationVersion"] == "0.9.0"
    assert index["createdUtc"] == "2026-08-18T12:00:00+00:00"
    assert "logs/app.log" in index["entries"]
    assert index["redaction"]["applied"] is True


def test_the_contents_index_is_itself_redacted() -> None:
    entries = _entries(BundleSource(name="notes.txt", text="jane.doe@brusa.biz"))
    assert "brusa.biz" not in entries[BUNDLE_CONTENTS_FILENAME]


def test_the_index_names_what_was_left_out_on_purpose() -> None:
    """A narrow bundle must not read as a broken one.

    Excluding the project document and AEDT's own logs is a decision, not an
    omission, and the person opening the archive cannot see the decision unless
    the index states it.
    """
    entries = _entries(BundleSource(name="logs/app.log", text="ok"))

    excluded = json.loads(entries[BUNDLE_CONTENTS_FILENAME])["redaction"]["excluded"]

    assert "project document" in excluded
    assert "AEDT log files" in excluded
    assert ".inductor.json" in excluded["project document"]
    assert REDACTED_EMAIL in entries["notes.txt"]


def test_no_sources_still_produces_the_contents_index() -> None:
    entries = _entries()
    assert list(entries) == [BUNDLE_CONTENTS_FILENAME]


def test_duplicate_names_after_redaction_stay_distinct() -> None:
    entries = _entries(
        BundleSource(name=r"C:\a\log.txt", text="one"),
        BundleSource(name=r"C:\b\log.txt", text="two"),
    )
    assert len(entries) == 3
```

```python
# tests/unit/adapters/system/test_diagnostic_archive.py
"""The security test: nothing forbidden survives into a real archive."""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

from inductor_designer.adapters.system.diagnostic_archive import (
    collect_bundle_sources,
    write_diagnostic_archive,
)
from inductor_designer.application.services.diagnostic_bundle import (
    build_bundle_entries,
)
from inductor_designer.application.services.redaction import RedactionContext

# Written independently of the production patterns on purpose: this list is the
# requirement, not a restatement of the implementation.
FORBIDDEN = (
    re.compile(r"[A-Za-z]:[\\/]"),
    re.compile(r"\\\\[A-Za-z0-9]"),
    re.compile(r"/home/"),
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"\b\d{1,5}@[A-Za-z0-9]"),
    re.compile(r"jane\.doe", re.IGNORECASE),
    re.compile(r"BRUSA-WS42", re.IGNORECASE),
    re.compile(r"BRUSA-FS01", re.IGNORECASE),
    re.compile(r"LICSRV01", re.IGNORECASE),
)

CONTEXT = RedactionContext(
    user_names=("jane.doe",), host_names=("BRUSA-WS42", "BRUSA-FS01")
)


def _seed(tmp_path: Path) -> tuple[Path, Path]:
    document = tmp_path / "project" / "boost.inductor.json"
    document.parent.mkdir(parents=True)
    document.write_text("{}", encoding="utf-8")
    run = document.parent / "runs" / "20260818-101500-maxwell-3d" / "results"
    run.mkdir(parents=True)
    (run.parent / "run-manifest.json").write_text(
        json.dumps(
            {
                "runId": "20260818-101500",
                "status": "failed",
                "diagnostics": [
                    r"Engine Detected Error: cannot open C:\Users\jane.doe\m.adp",
                    "licence checkout failed on 1055@LICSRV01",
                ],
                "artifacts": [{"kind": "aedt-project", "path": "runs/x/m.aedt"}],
            }
        ),
        encoding="utf-8",
    )
    (run / "solve-log.txt").write_text(
        "launch\tfailed\t" + r"\\BRUSA-FS01\share\m.aedt" + "\n", encoding="utf-8"
    )
    (run / "results.json").write_text('{"runId": "20260818-101500"}', encoding="utf-8")
    log_directory = tmp_path / "logs"
    log_directory.mkdir()
    log_path = log_directory / "inductor-designer.log"
    log_path.write_text(
        "2026-08-18\tWARNING\tinductor_designer\tmail jane.doe@brusa.biz on BRUSA-WS42\n",
        encoding="utf-8",
    )
    return document, log_path


def test_collect_reads_the_log_the_manifests_and_the_result_files(
    tmp_path: Path,
) -> None:
    document, log_path = _seed(tmp_path)

    names = [source.name for source in collect_bundle_sources(document, log_path)]

    assert any(name.endswith("inductor-designer.log") for name in names)
    assert any(name.endswith("run-manifest.json") for name in names)
    assert any(name.endswith("solve-log.txt") for name in names)


def test_the_project_document_never_becomes_an_entry(tmp_path: Path) -> None:
    """The document locates the runs directory; it is not itself collected.

    Ruled 2026-08-18. The parameter is a document path, so the cheapest wrong
    change in this file is to read it -- which would put user-authored text into a
    bundle built to be shareable. This test is the guard on that decision.
    """
    document, _ = _seed(tmp_path)
    document.write_text(
        '{"name": "a customer name no redactor can classify"}', encoding="utf-8"
    )

    sources = collect_bundle_sources(document, None)

    assert sources  # the runs beside it were still found
    assert all(document.name not in source.name for source in sources)
    assert all("no redactor can classify" not in source.text for source in sources)
    assert any(name.endswith("results.json") for name in names)


def test_the_project_document_is_not_collected(tmp_path: Path) -> None:
    document, log_path = _seed(tmp_path)

    names = [source.name for source in collect_bundle_sources(document, log_path)]

    assert not any(name.endswith("boost.inductor.json") for name in names)


def test_the_written_archive_carries_nothing_forbidden(tmp_path: Path) -> None:
    document, log_path = _seed(tmp_path)
    entries = build_bundle_entries(
        collect_bundle_sources(document, log_path),
        CONTEXT,
        application_version="0.9.0",
        created_utc="2026-08-18T12:00:00+00:00",
    )

    archive_path = write_diagnostic_archive(
        tmp_path / "out.diagnostics.zip", entries
    )

    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        assert names
        for name in names:
            payload = archive.read(name).decode("utf-8")
            for pattern in FORBIDDEN:
                assert pattern.search(name) is None, (pattern.pattern, name)
                assert pattern.search(payload) is None, (pattern.pattern, name)


def test_the_archive_still_carries_the_diagnosable_extension(tmp_path: Path) -> None:
    document, log_path = _seed(tmp_path)
    entries = build_bundle_entries(
        collect_bundle_sources(document, log_path),
        CONTEXT,
        application_version="0.9.0",
        created_utc="2026-08-18T12:00:00+00:00",
    )

    archive_path = write_diagnostic_archive(tmp_path / "o.diagnostics.zip", entries)

    with zipfile.ZipFile(archive_path) as archive:
        payload = "".join(
            archive.read(name).decode("utf-8") for name in archive.namelist()
        )
    assert "].adp" in payload
    assert "Engine Detected Error" in payload


def test_missing_sources_produce_an_archive_rather_than_an_error(
    tmp_path: Path,
) -> None:
    entries = build_bundle_entries(
        collect_bundle_sources(None, None),
        CONTEXT,
        application_version="0.9.0",
        created_utc="2026-08-18T12:00:00+00:00",
    )

    archive_path = write_diagnostic_archive(tmp_path / "e.diagnostics.zip", entries)

    with zipfile.ZipFile(archive_path) as archive:
        assert archive.namelist() == ["bundle-contents.json"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/application/test_diagnostic_bundle.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'inductor_designer.application.services.diagnostic_bundle'`

- [ ] **Step 3: Write the implementation**

```python
# src/inductor_designer/application/services/diagnostic_bundle.py
"""Build the shareable contents of a diagnostic bundle.

This is the second and last place that redacts (the first is the application
log formatter). Every entry's text *and* name passes through `redact_text` in
one loop, so an added source cannot skip redaction by accident, and the archive
writer accepts only what this function produced.

The project document is deliberately not a source: it carries a user-authored
project name and description, and diagnosis does not need them.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass

from inductor_designer.application.services.redaction import (
    REDACTED_EMAIL,
    REDACTED_HOST,
    REDACTED_LICENSE_SERVER,
    REDACTED_PATH,
    REDACTED_USER,
    RedactionContext,
    redact_text,
)

BUNDLE_CONTENTS_FILENAME = "bundle-contents.json"


@dataclass(frozen=True, slots=True)
class BundleSource:
    """One file read from disk, before redaction."""

    name: str
    text: str


@dataclass(frozen=True, slots=True)
class BundleEntry:
    """One redacted member of the archive."""

    name: str
    text: str


def _unique(name: str, taken: set[str]) -> str:
    """Redaction can collapse two distinct paths onto one name."""
    if name not in taken:
        return name
    for index in range(2, 1000):
        candidate = f"{name}.{index}"
        if candidate not in taken:
            return candidate
    raise ValueError(f"Too many bundle entries collide on {name!r}.")


def build_bundle_entries(
    sources: Sequence[BundleSource],
    context: RedactionContext,
    *,
    application_version: str,
    created_utc: str,
) -> tuple[BundleEntry, ...]:
    """Redacted entries, with a contents index first."""
    entries: list[BundleEntry] = []
    taken: set[str] = set()
    for source in sources:
        name = _unique(redact_text(source.name, context), taken)
        taken.add(name)
        entries.append(BundleEntry(name=name, text=redact_text(source.text, context)))
    index = json.dumps(
        {
            "applicationVersion": application_version,
            "createdUtc": created_utc,
            "entries": [entry.name for entry in entries],
            "redaction": {
                "applied": True,
                "markers": [
                    REDACTED_EMAIL,
                    REDACTED_HOST,
                    REDACTED_LICENSE_SERVER,
                    REDACTED_PATH,
                    REDACTED_USER,
                ],
                "removed": [
                    "absolute filesystem paths",
                    "machine names",
                    "licence server identifiers",
                    "user names",
                    "e-mail addresses",
                ],
            },
            # A support engineer must be able to tell a deliberately narrow
            # bundle from a broken one, and a user must be able to see what to
            # attach by hand if they judge it safe. Silence about an exclusion
            # reads as a missing file.
            "excluded": {
                "project document": (
                    "User-authored text -- project name, description, winding "
                    "labels, terminal intent -- cannot be classified by any "
                    "redaction rule. Every physical input is in the run "
                    "manifests instead. Attach the .inductor.json yourself if "
                    "you judge it safe to share."
                ),
                "AEDT log files": (
                    "Written by AEDT in a format this application does not "
                    "control, so their redaction cannot be proven. The desktop "
                    "messages captured during a failed run are in the "
                    "application log instead."
                ),
            },
        },
        indent=2,
        sort_keys=True,
    )
    return (
        # The index is redacted like everything else: an entry name that needed
        # redaction must not reappear in clear text here.
        BundleEntry(name=BUNDLE_CONTENTS_FILENAME, text=redact_text(index, context)),
        *entries,
    )
```

```python
# src/inductor_designer/adapters/system/diagnostic_archive.py
"""Read the bundle's sources from disk and write the archive.

Reading and zipping live here because they touch the filesystem; deciding what
is shareable lives in `application/services/diagnostic_bundle.py`. This module
never writes text it did not receive as a `BundleEntry`.
"""

from __future__ import annotations

import zipfile
from collections.abc import Sequence
from pathlib import Path

from inductor_designer.application.services.diagnostic_bundle import (
    BundleEntry,
    BundleSource,
)
from inductor_designer.application.services.run_directory import (
    MANIFEST_FILENAME,
    RESULTS_DIRECTORY_NAME,
    RUNS_DIRECTORY_NAME,
)

BUNDLE_SUFFIX = ".diagnostics.zip"
# A rotated log can be a megabyte; the tail is where the failure is.
_MAX_SOURCE_BYTES = 512_000
_RESULT_FILENAMES = ("solve-log.txt", "results.json", "results.csv")


def _read_tail(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if len(text) <= _MAX_SOURCE_BYTES:
        return text
    return (
        "[earlier lines omitted to keep the bundle small]\n"
        + text[-_MAX_SOURCE_BYTES:]
    )


def collect_bundle_sources(
    project_document_path: Path | None, log_path: Path | None
) -> tuple[BundleSource, ...]:
    """The application log and every run's evidence. Missing files are skipped.

    `project_document_path` is used only to find `runs/` beside it. The document
    itself is never opened, by the 2026-08-18 ruling: it holds user-authored text
    that no redaction rule can classify, and every physical input it carries is in
    the run manifests anyway. `test_the_project_document_never_becomes_an_entry`
    is what stops this from being "fixed" into reading it.
    """
    sources: list[BundleSource] = []
    if log_path is not None:
        for candidate in (log_path, *sorted(log_path.parent.glob(f"{log_path.name}.*"))):
            text = _read_tail(candidate) if candidate.is_file() else None
            if text is not None:
                sources.append(
                    BundleSource(name=f"logs/{candidate.name}", text=text)
                )
    if project_document_path is None:
        return tuple(sources)
    runs_root = project_document_path.resolve().parent / RUNS_DIRECTORY_NAME
    if not runs_root.is_dir():
        return tuple(sources)
    for directory in sorted(entry for entry in runs_root.iterdir() if entry.is_dir()):
        for relative in (
            Path(MANIFEST_FILENAME),
            *(Path(RESULTS_DIRECTORY_NAME) / name for name in _RESULT_FILENAMES),
        ):
            candidate = directory / relative
            text = _read_tail(candidate) if candidate.is_file() else None
            if text is not None:
                sources.append(
                    BundleSource(
                        name=f"runs/{directory.name}/{relative.as_posix()}",
                        text=text,
                    )
                )
    return tuple(sources)


def write_diagnostic_archive(path: Path, entries: Sequence[BundleEntry]) -> Path:
    """Write one deterministic, deflated archive of already-redacted entries."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for entry in entries:
            archive.writestr(entry.name, entry.text)
    return path
```

```python
# src/inductor_designer/ui/diagnostics_controller.py
"""Help > Save diagnostic bundle.

The bundle is written where the user asks. Nothing is uploaded, and nothing
leaves the machine on its own: the user chooses whether to share the file.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot

from inductor_designer import __version__
from inductor_designer.adapters.system.app_logging import LOGGER_NAME
from inductor_designer.adapters.system.diagnostic_archive import (
    BUNDLE_SUFFIX,
    collect_bundle_sources,
    write_diagnostic_archive,
)
from inductor_designer.application.services.diagnostic_bundle import (
    build_bundle_entries,
)

if TYPE_CHECKING:
    from inductor_designer.application.services.redaction import RedactionContext
    from inductor_designer.ui.project_session import ProjectSession


class DiagnosticsController(QObject):
    messageChanged = Signal()

    def __init__(
        self,
        session: ProjectSession,
        log_path: Path | None,
        context: RedactionContext,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._log_path = log_path
        self._context = context
        self._message = ""

    def _get_message(self) -> str:
        return self._message

    message = Property(str, _get_message, notify=messageChanged)

    def _get_suggested_file_name(self) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return f"diagnostics-{stamp}{BUNDLE_SUFFIX}"

    suggestedFileName = Property(str, _get_suggested_file_name, constant=False)

    @Slot(QUrl, result=bool)
    def saveBundle(self, target: QUrl) -> bool:
        path = Path(target.toLocalFile())
        try:
            entries = build_bundle_entries(
                collect_bundle_sources(self._session.document_path, self._log_path),
                self._context,
                application_version=__version__,
                created_utc=datetime.now(timezone.utc).isoformat(),
            )
            written = write_diagnostic_archive(path, entries)
        except Exception as error:  # noqa: BLE001 - the UI must never crash here
            logging.getLogger(LOGGER_NAME).warning("Bundle failed: %s", error)
            self._message = f"Unable to write the diagnostic bundle: {error}"
            self.messageChanged.emit()
            return False
        logging.getLogger(LOGGER_NAME).info(
            "Diagnostic bundle written with %d entries.", len(entries)
        )
        self._message = (
            f"Saved {written.name}. It contains no file paths, machine names, "
            "licence servers, user names, or e-mail addresses."
        )
        self.messageChanged.emit()
        return True
```

In `Main.qml`, add to the Help menu above `About`, plus the save dialog:

```qml
            MenuItem {
                objectName: "saveDiagnosticBundleMenuItem"
                text: qsTr("Save diagnostic bundle…")
                enabled: diagnosticsController !== null
                Accessible.name: text
                onTriggered: {
                    saveBundleDialog.currentFile = ""
                    saveBundleDialog.open()
                }
            }
```

```qml
    FileDialog {
        id: saveBundleDialog
        objectName: "saveBundleDialog"
        title: qsTr("Save diagnostic bundle")
        fileMode: FileDialog.SaveFile
        nameFilters: [qsTr("Diagnostic bundle (*.zip)")]
        onAccepted: diagnosticsController.saveBundle(selectedFile)
    }
```

Wire `DiagnosticsController(session, log_path, redaction_context)` in `main.py` and expose it as the `diagnosticsController` context property.

- [ ] **Step 4: Write the controller test**

```python
# tests/ui/test_diagnostics_controller.py
from __future__ import annotations

import os
import zipfile
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.adapters.system.diagnostic_archive import (  # noqa: E402
    BUNDLE_SUFFIX,
)
from inductor_designer.application.services.redaction import (  # noqa: E402
    RedactionContext,
)
from inductor_designer.ui.diagnostics_controller import (  # noqa: E402
    DiagnosticsController,
)
from inductor_designer.ui.project_session import ProjectSession  # noqa: E402
from tests.unit.domain.test_project import make_project  # noqa: E402

pytestmark = pytest.mark.ui


def _controller(tmp_path: Path) -> DiagnosticsController:
    QGuiApplication.instance() or QGuiApplication([])
    document = tmp_path / "boost.inductor.json"
    document.write_text("{}", encoding="utf-8")
    log_path = tmp_path / "logs" / "inductor-designer.log"
    log_path.parent.mkdir()
    log_path.write_text(r"warn C:\Users\jane.doe\b.aedt" + "\n", encoding="utf-8")
    session = ProjectSession(make_project(), document_path=document)
    return DiagnosticsController(
        session, log_path, RedactionContext(user_names=("jane.doe",))
    )


def test_saving_writes_a_redacted_archive(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    target = tmp_path / f"out{BUNDLE_SUFFIX}"

    assert controller.saveBundle(QUrl.fromLocalFile(str(target))) is True

    with zipfile.ZipFile(target) as archive:
        payload = "".join(
            archive.read(name).decode("utf-8") for name in archive.namelist()
        )
    assert "jane.doe" not in payload
    assert "no file paths" in controller.message


def test_an_unwritable_target_is_reported_not_raised(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    target = tmp_path / "missing-directory-file" / "x.zip"
    (tmp_path / "missing-directory-file").write_text("blocked", encoding="utf-8")

    assert controller.saveBundle(QUrl.fromLocalFile(str(target))) is False
    assert "Unable to write" in controller.message


def test_the_suggested_name_carries_the_bundle_suffix(tmp_path: Path) -> None:
    assert _controller(tmp_path).suggestedFileName.endswith(BUNDLE_SUFFIX)
```

- [ ] **Step 5: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/application/test_diagnostic_bundle.py tests/unit/adapters/system -q`
Expected: PASS

Run: `set QT_QPA_PLATFORM=offscreen && set QSG_RHI_BACKEND=software && .venv/Scripts/python.exe -m pytest tests/ui -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/inductor_designer/application/services/diagnostic_bundle.py src/inductor_designer/adapters/system/diagnostic_archive.py src/inductor_designer/ui tests
git commit -m "feat(diagnostics): write a shareable redacted diagnostic bundle"
```

---

### Task 9: Forced-failure evidence and acceptance

**Files:**
- Create: `tests/integration/test_reliability_recovery.py`
- Create: `docs/development/m9-reliability-evidence.md`
- Modify: `docs/development/ROADMAP.md` (the Milestone 9 section)
- Modify: `docs/superpowers/plans/README.md` (current status and the remaining sequence)

**Interfaces:**
- Consumes: the whole milestone. No code interface.

- [ ] **Step 1: Write the forced-failure integration test**

`tests/integration/test_reliability_recovery.py` drives four forced failures end to end against the real catalog, the real material overlay, and the recording exporter fakes in `tests/fakes/`. No AEDT, no FEMM.

1. **A save that fails preserves the last valid project.** Bind a `save_callback` that raises `OSError`, apply an edit, call `saveProject()`, and assert: it returns `False`, `session.project` still holds the edit, `session.dirty` is `True`, the status message names the failure, and the recovery snapshot written by `flushAutosave()` still loads back as the edited project.
2. **A killed solve is reconciled, never re-solved.** Seed a run directory with a `"status": "running"` marker and a saved `Inductor3D.aedt`, call `reconcile_unfinished_runs`, and assert: the manifest reads `interrupted`, `results` is `null`, both `run.interrupted_before_completion` and `run.artifact_saved_but_unsolved` appear, the `.aedt` still exists, and the recording exporter recorded **zero** calls — recovery reached no adapter.
3. **A licence failure produces actionable, redactable evidence.** Make the recording Maxwell 3D exporter fail its `launch` stage with `License checkout failed on 1055@LICSRV01`, run `start_project_run`, and assert: `ProjectRunFailed` carries a manifest with `status: failed`, its diagnostics contain the raw text *and* `license.unavailable: ...`, and a bundle built from that run directory contains the advice code but neither `1055@LICSRV01` nor any absolute path.
4. **Undo restores the last valid project after a rejected edit.** Apply a valid edit, attempt an edit the domain rejects (overlapping winding sectors), and assert the session still holds the valid project, that `undo()` returns to the state before the valid edit, and that `canGenerate` on a `SimulationController` follows `dirty` in both directions.

- [ ] **Step 2: Run the complete non-live gate**

```bash
.venv/Scripts/python.exe -m ruff check .
```

Expected: `All checks passed!`

```bash
.venv/Scripts/python.exe -m mypy src tools
```

Expected: `Success: no issues found`

```bash
.venv/Scripts/python.exe -m tools.check_architecture
```

Expected: clean exit, no output

```bash
.venv/Scripts/python.exe -m pytest -m "not aedt and not femm"
```

Expected: all passed, none failed; record the exact count and duration. Run it once more as `-n 8` for speed when iterating, but the recorded number is from the command above.

```bash
git diff --check
```

Expected: no output

- [ ] **Step 3: Run the manual forced-failure walk on the Windows workstation**

This is the part only a person can do, and it is what Fabio Posser verifies. **One AEDT session at a time:** confirm no `ansysedt.exe` is running before starting.

1. Start the application on a saved project, edit a winding, and kill the process from Task Manager without saving. Restart: the recovery dialog offers the autosaved changes, `Recover` restores them, the project on disk is untouched, and `Generate` stays disabled until the project is saved.
2. Repeat, and choose `Discard`: the on-disk project is what loads, and the snapshot is gone.
3. Start a `Generate and Solve` run on Maxwell 3D, and kill the process while the `analyze` stage is visible. Restart and open the project: the Review screen names the interrupted run, `run-manifest.json` in that directory reads `"status": "interrupted"` with both diagnostics, the saved `*.aedt` is still there, and there is no control anywhere offering to resume it. Start a new run: it lands in a new directory and succeeds.
4. `Help > Save diagnostic bundle…`, save it, and open the `.zip`. Read every member. Confirm no drive letter, no UNC path, no machine name, no user name, no licence server, and no e-mail address, and that `bundle-contents.json` lists both what was removed and what was excluded on purpose. Confirm the failure text and its advice code are still readable, and that the AEDT message lines captured when the stage failed are in the log entry -- that is the evidence AEDT's own log files were excluded without losing the reason a solve died.
5. Edit, then `Edit > Undo` and `Edit > Redo` across all five screens — core, material pin, windings, operating point, simulation recipe — and confirm each screen redraws and that undoing back to the saved state re-enables `Generate`.

- [ ] **Step 4: Write the evidence document**

`docs/development/m9-reliability-evidence.md` records, each as its own short section: the non-live gate output with exact counts; for each of the five manual steps, what was done and what was observed; the verbatim `run-manifest.json` of the interrupted run; and the complete member list of one real diagnostic bundle with the redaction confirmation. Note explicitly that M9 makes no new live-solver claim and repeats no accepted M8 evidence.

- [ ] **Step 5: Update the roadmap and the plan index**

In `docs/development/ROADMAP.md`, under Milestone 9, record that implementation is complete and awaiting Fabio Posser's verification, link this plan and the evidence document, and list the four decisions he ruled on from the open-questions section below. In `docs/superpowers/plans/README.md`, add M9 to the current status with the same wording used for M8a–M8c, and note that the next detailed plan is M10, Windows Release, whose entry condition is M9 acceptance.

- [ ] **Step 6: Commit**

```bash
git add docs tests/integration/test_reliability_recovery.py
git commit -m "docs: record M9 reliability evidence"
```

---

## Acceptance evidence for Fabio Posser

The M9 exit criterion is *forced UI and solver failures preserve the last valid Project document and produce sufficient redacted evidence for diagnosis.* He can verify exactly this, without reading any code:

1. **The non-live gate**, four commands, all clean:
   - `.venv/Scripts/python.exe -m ruff check .`
   - `.venv/Scripts/python.exe -m mypy src tools`
   - `.venv/Scripts/python.exe -m tools.check_architecture`
   - `.venv/Scripts/python.exe -m pytest -m "not aedt and not femm"`
2. **A killed application** loses no valid project: restart offers the autosaved changes, `Recover` restores them, and the file on disk was never modified behind his back.
3. **A killed solve** shows up as `"status": "interrupted"` with no results and no partial-success claim, its saved-but-unsolved `*.aedt` is still on disk, and the application offers a new run rather than a resume.
4. **One diagnostic bundle**, opened and read member by member, carries the failure text and its advice code and carries no path, machine name, licence server, user name, or e-mail address.
5. **Undo and redo** work across all five Guided Studio screens, and undoing back to the saved state re-enables `Generate`.

## Open questions for Fabio Posser

These are product rulings, not implementation choices. Each names what the plan does until he rules and what changes when he does. None of them changes the task structure.

Questions 6 and 7 were ruled on 2026-08-18 and stay here, struck through, so the reasoning lives with the question and not only in the commit that settled it. Seven remain open, all with a working default.

1. **Autosave interval.** How much unsaved work may a crash cost? The plan uses a 2000 ms debounce after the last valid edit (`AUTOSAVE_DEBOUNCE_MS` in `ui/project_session.py`). A ruling changes one constant.
2. **Recovery snapshot location.** The plan writes it to `%LOCALAPPDATA%\InductorDesigner\recovery\`, so a shareable project directory never collects stray autosave files and a read-only project directory still autosaves. The alternative is beside the project document, where the user can see it. A ruling changes `recovery_directory()` in `adapters/system/environment.py`.
3. **Undo depth.** The plan bounds the history at 50 project snapshots (`UNDO_DEPTH`). A ruling changes one constant.
4. **Recovery prompt versus silent restore.** The plan prompts once at startup with `Recover` / `Discard` and never restores silently. A ruling would change `Main.qml`'s `Component.onCompleted` branch only.
5. **Whether the bundle is also written automatically on a failed run.** The plan writes a bundle only when the user asks for one from the Help menu; a failed run already leaves its own run directory. A ruling would add one call in `project_run.py`'s failure path.
6. ~~Whether the bundle may contain the Project document.~~ **Ruled 2026-08-18: excluded.** Reasoning in the bundle-contents decision above.
7. ~~Whether the bundle may contain AEDT's own log files.~~ **Ruled 2026-08-18: excluded, with the desktop message channel captured through this application's own redacting logger instead.** Reasoning in the bundle-contents decision; implementation in Task 3 Step 0.
8. **Whether reconciliation of an interrupted run is automatic.** The plan reconciles at startup and on Open, so a stale `running` manifest can never be read as a live run. The alternative is reconciling only when the user asks, which leaves an untruthful document on disk until they do.
9. **How long interrupted run directories are kept.** The plan never deletes one: it is the user's evidence. A retention rule (age, count) would need its own ruling and its own visible message before anything is removed.

## Known risks

1. **The advice substrings are unproven text.** `simulation/failure_advice.py` matches wording observed from AEDT 2025 R2, pyFEMM and CPython as of 2026-08-18, but no test can prove AEDT still phrases a licence failure that way. The failure mode is benign and bounded: an unmatched diagnostic becomes `run.unclassified_failure`, which says so honestly, and the raw diagnostic is always kept beside the advice. Correcting the table touches one tuple and no caller. This is the same isolation strategy M8b used for the Maxwell expression names.
2. **`dirty` becomes a value comparison.** `InductorProject` equality now gates the `Generate` button. All of its members are frozen dataclasses and tuples, so equality is structural, but a future mutable member would silently make comparison identity-based and leave `Generate` disabled after an undo. Task 4's `test_undo_back_to_the_saved_project_clears_dirty` is the guard; keep it.
3. **A directory with no manifest is claimed as interrupted.** `find_unfinished_runs` treats any run directory without a readable `run-manifest.json` as interrupted. If a future writer creates a run directory long before its marker, a healthy in-flight run could briefly be reported as interrupted in another window. `start_project_run` writes the marker immediately after `allocate_run_directory`, so the window is microseconds today; a future change that widens it must revisit this.
4. **Redaction cannot recognise a user-authored string.** A project name, a winding label, or a terminal-intent string typed by the user could name a person, and no regular expression can tell. This is exactly why the plan excludes the project document from the bundle and why open question 6 exists. Run manifests carry winding ids and physical values, not free text — that is worth re-checking whenever the manifest grows a field.
5. **Autosave and a solve compete for the same project.** The generation worker reads the project through the lock-protected `CurrentProjectProvider`, and autosave writes a separate file, so there is no shared mutable state. But the `Generate` gate means a run only ever starts from a clean project, and an edit during a run makes the project dirty while the run continues against the value it captured. That is existing M7c/M8a behaviour and M9 does not change it; it is listed here because a reviewer will ask.
6. **The Windows-only fallback path.** `application_data_directory()` falls back to `~/.local/share` when `LOCALAPPDATA` is unset, purely so the non-solver suite runs on the Linux CI runner. It is not a supported product configuration (ADR 0004) and must not grow features.
7. **No new live-solver evidence.** M9 relies on the accepted M8 live runs and adds none. The only live-adjacent verification is the manual forced-kill walk in Task 9 Step 3, which needs a real solve to interrupt — and therefore the single-AEDT-session rule.

## Self-Review

**Spec coverage against the four approved ROADMAP bullets.** Autosave — Task 5. Crash recovery — Tasks 5 and 6. Application-wide undo/redo — Task 4. Recover interrupted runs without claiming partial success — Task 7, with the never-re-solve rule stated in the module docstring, in the reconciled diagnostics, and in the Task 7 UI test that asserts the word "resume" appears nowhere. Actionable installation, license, material, file and convergence errors — Task 3, one code per subject, wired at the single manifest-diagnostic assembly point and at the convergence quantity. Redacted logs — Task 2. Diagnostic bundle — Task 8. Robustness tests for cancellation, failed stages and recovery (realignment section 10, M9) — Task 9, plus the existing M8a cancellation tests, which Task 7 does not disturb because a cancelled run already writes `RunStatus.CANCELLED` and is deliberately excluded from `_UNFINISHED_STATUSES`.

**Placeholder scan.** No TBD, no "add error handling", no "similar to Task N". Every code step carries its code, every test step carries its assertions, every command carries its expected output. The one genuinely unprovable element — the advice substrings — is named in Task 3's docstring and in known risk 1, with its bounded failure mode, which is a stated risk rather than a placeholder.

**Type consistency.** `RedactionContext` and `redact_text` are defined in Task 1 and used under those names in Tasks 2 and 8. `recovery_directory`, `log_directory`, `environment_redaction_context`, `LOGGER_NAME` and `APP_LOG_FILENAME` are defined in Task 2 and consumed in Tasks 5, 6, 7 and 8. `AdviceCode`, `FailureAdvice`, `advise` and `convergence_advice` are defined in Task 3 and consumed there. `UNDO_DEPTH`, `apply`, `undo`, `redo`, `canUndo`, `canRedo` and `applyRecovered` are defined in Tasks 4 and 6 on one class. `RecoveryStore`, `RecoverySnapshot`, `RECOVERY_INDEX_FILENAME` and `RECOVERY_DOCUMENT_FILENAME` are defined in Task 5 and consumed in Task 6. `UnfinishedRun`, `find_unfinished_runs`, `reconcile_unfinished_runs`, `INTERRUPTED_DIAGNOSTIC` and `UNSOLVED_ARTIFACT_DIAGNOSTIC` are defined in Task 7 and consumed in Task 7's UI test and Task 9. `BundleSource`, `BundleEntry`, `build_bundle_entries`, `collect_bundle_sources`, `write_diagnostic_archive` and `BUNDLE_SUFFIX` are defined in Task 8 and consumed there and in Task 9.

**Boundary check.** `simulation/failure_advice.py` imports only `dataclasses`. `application/services/redaction.py` imports only `re` and `dataclasses`; `diagnostic_bundle.py` adds `json` and `collections.abc`. Neither imports `inductor_designer.adapters`. Every filesystem and platform call lives under `adapters/system/` or `adapters/persistence/`. `tools/check_architecture.py` is run in Tasks 1, 2, 7 and 9.

**Known deviation to raise at review.** Task 3 inserts advice into `_build_manifest`, which means every failed manifest's `diagnostics` list doubles in length: raw line, advice line, raw line, advice line. A reviewer may prefer a separate `advice` field on `RunManifest` instead. That would be a manifest-document change and therefore an M8-contract change, which M9's entry condition forbids without a documented decision — so the plan appends into the existing field and flags the alternative here rather than deciding it mid-implementation.
