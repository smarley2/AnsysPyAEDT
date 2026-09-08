# Per-project recovery slot and an advisory project lock

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop two application windows from silently destroying each other's work. Two defects, one cause — nothing in the application knows another instance exists.

**Origin:** Both were found after Milestone 9's whole-branch review, by Fabio Posser asking whether opening one project twice should be blocked. Neither is in M9's scope, and M9 is awaiting his verification, so they are deliberately kept out of that milestone rather than bolted onto a record that has already been reviewed.

**Entry condition:** none. Both tasks sit on M9's own machinery (`RecoveryStore`, `ProjectSession`, `run_recovery`) and change no physics, no schema, no solver path.

## The two defects

**1. The recovery slot is global, not per-project.** `adapters/persistence/recovery_store.py` names its two files with the fixed constants `RECOVERY_INDEX_FILENAME` and `RECOVERY_DOCUMENT_FILENAME`, so every `RecoveryStore` built against `recovery_directory()` writes the same pair. Two windows editing **two different projects** therefore share one slot: whichever autosaves last wins, and because `RecoveryController._offerable` only offers a snapshot whose `document_path` matches the session's, the loser's unsaved work is not even offered — it is silently gone. This needs no second window on the *same* project, and it is a data-loss path, not a race.

**2. Nothing prevents two windows on the same project.** Both save to the same file, so the last writer wins. Worse, `main.py` reconciles unfinished runs unconditionally at startup, and `_is_run_busy` is process-local: window B's startup reconcile rewrites window A's **live** `running` manifest to `interrupted` with `results: null`. That self-heals when A writes its final manifest, so the damage is display-only — but it is the same race Task 7 closed *within* one process, still open across processes.

Defect 1 is fixed first, because it loses work rather than merely confusing a display, and because a per-project slot makes the lock's job narrower.

## Global constraints

- Filesystem and process access belongs in `adapters/`; `domain`, `geometry`, `materials` and `simulation` import no OS module. `tools/check_architecture.py` enforces it.
- No physics, schema, catalog value, unit or approximation changes.
- Add or update tests before implementing.
- Diagnostic and reason codes stay lowercase dotted `<subject>.<reason>`; never reuse or repurpose one.
- A recovery path that refuses to start the application is worse than no recovery — the rule Task 6 established, and it governs the lock too.
- All code, comments, commits and UI copy in English.
- Gate: `ruff check .`, `mypy src tools`, `python -m tools.check_architecture`, `pytest -n 8 -m "not aedt and not femm"`. No new live-solver test.

---

### Task 1: One recovery slot per project document

**Files:**
- Modify: `src/inductor_designer/adapters/persistence/recovery_store.py` — per-document filenames
- Modify: `src/inductor_designer/ui/main.py` — unchanged wiring, verify it still binds one store
- Test: `tests/unit/adapters/persistence/test_recovery_store.py`
- Test: `tests/ui/test_autosave.py`, `tests/ui/test_crash_recovery.py` — existing behaviour must hold

**Interfaces:**
- `RecoveryStore.__init__(directory, repository)` keeps its signature. `index_path` and `document_path` become functions of the document being autosaved, not constants.
- Add `RecoveryStore.slot_for(document_path: Path | None) -> RecoverySlot`, where a slot carries the two paths for one document. `write`, `read`, `load_project` and `clear` all take the document path they concern.

**The naming rule.** A slot is named from a stable hash of the **resolved** document path, not from its filename: two projects called `boost.inductor.json` in different folders must not collide, and the same project opened by an absolute and a relative path must land in the same slot (Task 6 already resolves both sides for exactly this reason). A short hex digest keeps the name free of the path itself, which matters because this directory's contents must stay shareable-adjacent — a filename is not redacted by anything.

An unsaved project (`document_path is None`) keeps one reserved slot, since there is nothing to key on and only one such project can exist per window.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/adapters/persistence/test_recovery_store.py
def test_two_documents_do_not_share_one_slot(tmp_path: Path) -> None:
    """The defect this task exists for: one global slot meant the second
    project's autosave overwrote the first's, and because the recovery offer
    only fires when the document path matches, the first project's unsaved
    work was not even offered -- it was gone."""
    store = _store(tmp_path)
    first = tmp_path / "a" / "boost.inductor.json"
    second = tmp_path / "b" / "boost.inductor.json"

    store.write(replace(make_project(), description="first"), first, now=NOW)
    store.write(replace(make_project(), description="second"), second, now=NOW)

    assert store.load_project(store.read(first)).description == "first"
    assert store.load_project(store.read(second)).description == "second"


def test_the_same_document_by_two_spellings_is_one_slot(tmp_path: Path) -> None:
    """`main.py` passes `args.project` unresolved, so a relative launch and an
    absolute one must not produce two snapshots of one project."""


def test_clearing_one_slot_leaves_the_other(tmp_path: Path) -> None:
    """A save in one window must not discard the other window's recovery copy."""


def test_an_unsaved_project_keeps_its_own_reserved_slot(tmp_path: Path) -> None:
    """`document_path is None` has nothing to key on; it must still not collide
    with a saved project's slot."""
```

- [ ] **Step 2: Implement the per-document slot**

Derive the slot from `hashlib.sha256(str(path.resolve()).casefold().encode())`, taking the first 16 hex characters. Case-folded because Windows paths are case-insensitive and `WindowsPath.__eq__` already compares that way — without it, `C:\W\boost` and `c:\w\boost` would be two slots for one file.

- [ ] **Step 3: Update every caller**

`ProjectSession`'s autosave callback and `recovery_cleanup`, and `RecoveryController`. The controller already knows the session's document path; pass it through rather than letting the store guess.

- [ ] **Step 4: Prove the old defect cannot return**

Keep `test_two_documents_do_not_share_one_slot` as the regression guard, and verify by mutation that reverting to a constant filename turns it red.

**Acceptance:** two windows on two projects each recover their own work; a save in one leaves the other's snapshot intact; the same document by two spellings is one slot.

---

### Task 2: An advisory lock on the open project

**Files:**
- Create: `src/inductor_designer/adapters/system/project_lock.py`
- Modify: `src/inductor_designer/ui/main.py` — acquire on launch, release on exit
- Modify: `src/inductor_designer/ui/project_session.py` — acquire on Open, release the previous
- Modify: `src/inductor_designer/ui/qml/Main.qml` — the already-open message
- Test: `tests/unit/adapters/system/test_project_lock.py`
- Test: `tests/ui/test_project_lock_wiring.py`

**Interfaces:**
- `ProjectLock(document_path: Path)` with `acquire() -> LockOutcome` and `release() -> None`.
- `LockOutcome` states: `ACQUIRED`, `TAKEN_FROM_STALE`, `HELD_BY_LIVE_PROCESS`.
- Lock file `<document>.inductor.json.lock` holding pid, host name and an ISO start time. Same convention AEDT uses (`.aedt.lock`), and `*.aedt.lock` is already git-ignored — add `*.inductor.json.lock` beside it.

**THE RULE THAT MATTERS.** A stale lock must never block the application. The normal aftermath of the crash this whole area exists to survive is a lock file whose owner is dead, so:

- lock absent → acquire;
- lock present, recorded pid **not alive** on this host → take it, log that a stale lock was cleared;
- lock present, recorded pid **alive** → refuse, and say which window holds it.

A lock from a *different* host cannot be probed for liveness. Treat it as live and refuse, since a project on a network share genuinely may be open elsewhere — but say so distinctly, because the user can override by closing the other machine's window and there is nothing else they can do.

Liveness on Windows: `OpenProcess` via `ctypes`, or the narrower `os.kill(pid, 0)` guarded for `PermissionError` (which means the process exists but is not ours — still alive). Do not use a bare `psutil` dependency for this; it is not in the project's dependencies and one syscall does not justify adding it.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/adapters/system/test_project_lock.py
def test_a_free_document_is_acquired(tmp_path: Path) -> None: ...


def test_a_lock_held_by_this_live_process_is_refused(tmp_path: Path) -> None:
    """Two windows on one project: both save to the same file, so the last
    writer silently wins, and window B's startup reconcile rewrites window A's
    live `running` manifest."""


def test_a_stale_lock_is_taken_rather_than_blocking(tmp_path: Path) -> None:
    """The rule Task 6 established: a recovery path that refuses to start is
    worse than no recovery. A dead owner's lock is the ORDINARY state after the
    crash this area exists to survive, so it must never wedge the application."""
    _write_lock(tmp_path, pid=_a_pid_that_is_not_running())

    assert ProjectLock(document).acquire() is LockOutcome.TAKEN_FROM_STALE


def test_a_lock_from_another_host_is_refused_distinctly(tmp_path: Path) -> None:
    """Liveness cannot be probed across hosts, so it is treated as live -- but
    the message has to differ, because the remedy is on another machine."""


def test_a_malformed_lock_file_does_not_block(tmp_path: Path) -> None:
    """Same reasoning as the naive-timestamp defect in M9 Task 6: an
    unparseable file left by another build must not prevent startup."""


def test_releasing_removes_only_our_own_lock(tmp_path: Path) -> None:
    """Releasing a lock this process does not own would hand the document to a
    third window while the real owner is still editing."""
```

- [ ] **Step 2: Implement `ProjectLock`**

Write the lock with the same mkstemp-then-`os.replace` shape used by `ProjectRepository.save` and `RecoveryStore._write_atomic`, so a torn lock cannot exist. Release only if the file still records this pid and host.

- [ ] **Step 3: Wire it into launch and Open**

`main.py` acquires before building the session. On `HELD_BY_LIVE_PROCESS`, report and exit with a distinct code rather than opening a second editable window — and say which pid holds it. On Open, `ProjectSession` acquires the new document's lock before swapping, and releases the previous one only once the new acquisition succeeded; a refused Open must leave the current document open and untouched.

- [ ] **Step 4: Release on every exit path**

Clean exit, `Exit` menu item, window close, and an unhandled exception. A lock leaked by a crash is handled by the stale path, so this is about not leaving one behind when the application exits normally.

- [ ] **Step 5: Close the cross-process reconcile race**

With the lock in place, `main.py`'s unconditional startup reconcile is safe for the same project: a second window cannot reach it. Update the comment at that call site, which currently says "nothing can be busy before any run has started" — true within one process, and now true across them for a locked document. State the residual: two windows on *different* projects in the same folder still share a `runs/` root, so add the document-path check to reconciliation or note why it is not needed.

**Acceptance:** a second window on the same project is refused with a clear message; a stale lock never blocks; a refused Open leaves the current project untouched; no lock survives a clean exit.

---

## Open questions for Fabio Posser

1. **Read-only second window, or refuse outright?** The plan refuses. A read-only mode is a larger change — every editable control would need gating — and nothing here needs it. A ruling changes Task 2 Step 3 only.
2. **What should happen to an existing recovery snapshot when the slot naming changes?** The plan orphans them: an old global-slot snapshot is simply never read again, and the directory keeps two harmless files. Deleting them on first launch is one call; migrating them needs a document path the old index already records, so migration is possible if he prefers it.

## Known risks

1. **Pid reuse.** A stale lock whose pid has been reused by an unrelated process reads as live, and the user is refused. Rare, and it fails toward refusing rather than toward two writers. The recorded start time makes it detectable if it ever matters.
2. **A network share cannot be probed.** A lock from another host is always treated as live, so a crashed remote window leaves the project blocked until someone clears the file. Stated in the message rather than worked around, since the alternative is guessing.
3. **The slot digest is not reversible.** Support cannot tell which project a snapshot belongs to by looking at the directory. The index inside each slot still records the document path, so the information is there — one file open away, not lost.
