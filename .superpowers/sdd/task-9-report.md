# M5a Task 9 Report — Material Record Reproduction

## Status

Implemented the Task 9 reproducibility engine from dependency baseline `69109a9`.

## Ownership and scope

- Owner: Codex Task 9 implementer.
- Added `src/inductor_designer/materials/replay.py` and
  `tests/unit/materials/test_replay.py`.
- Added the shared `canonicalize_points` helper to `materials/serde.py` and changed the
  Task 8 CSV import service to reuse it.
- Dependencies: material records, calibration/extraction, fitting, deterministic serde,
  canonical units, and Task 8 import/draft creation through commit `69109a9`.
- No adapters, schemas, catalogs, solver code, or external dependencies changed.

## TDD evidence

The replay tests were written first. The initial focused run failed because the declared
module did not exist:

```text
.venv/bin/python -m pytest tests/unit/materials/test_replay.py -q
ModuleNotFoundError: No module named 'inductor_designer.materials.replay'
1 error in 0.20s
```

An additional no-early-return regression was also observed red before its fix:

```text
test_missing_image_does_not_prevent_independent_extraction_check
FAILED: expected the independent series mismatch after the missing-image mismatch
1 failed in 0.16s
```

The focused replay suite then passed with `8 passed`.

## Acceptance evidence

- `ReproductionReport` is a frozen slots dataclass and exposes ordered immutable
  mismatch messages.
- Every provenance source is checked for missing bytes or an exact SHA-256 mismatch.
- CSV bytes are decoded, parsed, converted to canonical units, sorted, and rounded through
  the same materials helper used by Task 8.
- Image series replay their stored extraction transform and use the same canonical helper.
- Stored points are compared exactly; valid reconstructed loss points drive a fresh exact
  `fit_steinmetz` comparison; the record revision is recomputed last.
- Independent divergences are accumulated without an early return. Missing or hash-invalid
  CSV data does not emit derivative series/fit noise, while image extraction remains
  independently checkable because it is fully recorded.
- Tests isolate source, stored-point, fit, and revision tampering, and also prove combined
  mismatch order and missing-source cascade suppression.

## Independent review

The required independent review reported no Critical, Important, or Minor findings. It
confirmed the shared canonicalization boundary, no-early-return behavior, mismatch cascade
suppression, both reconstruction paths, exact fit equality, and revision replay.

## Required full gates

- `.venv/bin/python -m pytest tests -q -m "not aedt and not ui and not femm"`
  - `490 passed, 9 deselected`
- `.venv/bin/python -m ruff check .`
  - `All checks passed!`
- `.venv/bin/python -m mypy`
  - `Success: no issues found in 85 source files`
- `.venv/bin/python tools/check_architecture.py`
  - Exit code 0, no output.
- `git diff --check`
  - Exit code 0, no output.

## Commit

`feat(materials): reproduce records from sources and transformation history`

## Concerns

None.
