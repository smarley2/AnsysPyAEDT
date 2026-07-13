# Foundation Validation Plan

## Purpose and current status

This plan tells an operator how to collect the remaining evidence for Milestone 0 without relying on conversation history. The foundation implementation and validation infrastructure exist. Hosted non-AEDT CI success is recorded below; real AEDT execution and Milestone 0 completion are not recorded.

No supported AEDT 2024 R2 or 2025 R2 Student executable is installed on the development machine. The 2025.2 Commercial row is reviewed and passed; the other three rows are `out-of-scope` for this milestone (no machine, no license). They become required again if a future milestone targets a Student or 2024 R2 release.

## Scope and release/edition matrix

Collect reviewed evidence for every required row:

| Release target | Edition | Runner release value |
| --- | --- | --- |
| AEDT 2024 R2 | Commercial | `2024.2` |
| AEDT 2024 R2 | Student | `2024.2` |
| Latest installed AEDT | Commercial | Exact installed `YYYY.R` value |
| Latest installed AEDT | Student | Exact installed `YYYY.R` value |

The latest installed Commercial and Student releases may differ. Record the exact release used for each row during matrix review.

## Phase A: Hosted non-AEDT CI

Recorded evidence:

- [GitHub Actions run 29234286379](https://github.com/smarley2/AnsysPyAEDT/actions/runs/29234286379) passed for commit `1f24ff3`.
- The successful jobs were quality, Windows Python 3.10, Windows Python 3.13, Ubuntu Python 3.10, and Ubuntu Python 3.13.
- The quality job ran Ruff, mypy, and architecture checks. Each test job installed UI dependencies and ran the non-AEDT coverage suite defined by the [hosted CI workflow](../../.github/workflows/ci.yml).

This run satisfies the hosted non-AEDT CI evidence requirement for Task 11. It does not satisfy the local clean-environment gates or any controlled AEDT requirement.

## Phase B: Local clean-environment release gates

From a clean checkout and fresh virtual environment, run the exact Task 11 non-AEDT release gates:

```powershell
python -m pip install -e ".[dev,ui]"
python -m ruff check .
python -m mypy src tools
python -m tools.check_architecture
python -m pytest -m "not aedt" --cov=inductor_designer --cov-report=term-missing
```

The installation must succeed; Ruff, mypy, and the boundary checker must exit successfully; all selected tests must pass; and branch-aware coverage must be at least 80 percent.

Then run the Task 11 repository-hygiene checks:

```powershell
git status --short
git check-ignore artifacts/compatibility/example/evidence.json example.aedt
```

Review `git status` for only intentional handoff edits and confirm that both generated-artifact examples are reported as ignored. Do not proceed with unexpected solver output, credentials, license details, or unrelated files in the worktree.

## Phase C: Controlled AEDT runs

Follow the full [AEDT compatibility procedure](aedt-compatibility-testing.md) on a Windows machine with the exact release and edition under test, an appropriate license, and the AEDT development dependencies installed.

Use this command pattern from the repository root for each row:

```powershell
.\tools\run_aedt_spike.ps1 -Release <YYYY.R> -Edition <commercial|student> -Graphical
```

Run `2024.2` once for each edition. Then run each latest-installed row with that edition's exact installed release value. Use graphical mode first so startup and edition behavior are observed rather than assumed.

For every run, retain the generated `evidence.json` and Maxwell projects outside Git long enough for review. Confirm that the runner exits successfully when the spike succeeds, `requestedEnvironment` matches each artifact's `observedSession`, the exact PyAEDT version is present, and both Maxwell 2D and Maxwell 3D artifact results are complete. Stop without updating the matrix if an observed session differs from the requested release or edition. Check evidence for personal paths, license information, credentials, or other sensitive machine details before sharing it.

## Phase D: Manual inspection and matrix update

For each controlled run:

1. Open both generated projects and confirm that the named rectangle or box exists.
2. Confirm that each project saved, closed, and reopens without a repair warning.
3. Inspect Maxwell 3D for the Include DC Fields capability and record only the observed result in `manualReview.includeDcFields3d`.
4. Record reproducible Student restrictions in `manualReview.discoveredLimits` without personal, license-server, or machine-path details; add the reviewer GitHub handle and ISO-8601 UTC time to `manualReview.reviewedBy` and `manualReview.reviewedAt`. The generated fields start null or empty and `capabilities.reviewStatus` remains `unreviewed`.
5. Review all evidence, then update only the matching row in the [AEDT compatibility matrix](../../compatibility/aedt-matrix.yml) to `passed` or `failed`.
6. Copy manually reviewed capability values from evidence and add the exact PyAEDT version, ISO-8601 UTC review time, and reviewer GitHub handle.
7. Delete local generated artifacts after review when they are no longer needed; never commit them.

If a latest-installed row used a concrete release, replace `latest-installed` only in that matching row with the exact reviewed `YYYY.R` value.

## Acceptance and gating rules

- Never infer AEDT or PyAEDT support, Include DC Fields availability, or Student restrictions from version numbers.
- Hosted evidence must cover Windows and Linux on Python 3.10 and 3.13.
- Local clean-environment gates must pass with at least 80 percent branch-aware coverage.
- Every **required** controlled AEDT row must contain reviewed evidence. Milestone 0 cannot close while any required row remains `unverified`. Rows marked `out-of-scope` are not required and are revisited only when a later milestone changes the support matrix.
- A `failed` row is valid observed evidence, but it does not establish support. Its cause, compatibility policy, and effect on the Milestone 0 exit criterion must be documented and accepted before closure.
- Task 11 remains pending until all four controlled rows have reviewed evidence and the other Milestone 0 gates are satisfied.
- Milestone 1 planning and implementation remain blocked until Milestone 0 is formally accepted.
- Generated AEDT projects and raw local evidence remain outside Git.

## Operator checklist

- [ ] Use a clean checkout and fresh virtual environment.
- [x] Complete and review the hosted quality job and all four non-AEDT test-matrix jobs.
- [ ] Run the Phase B release and hygiene commands exactly as shown.
- [ ] Prepare a supported licensed Windows AEDT environment for each required release and edition.
- [ ] Run the graphical controlled spike for all four rows.
- [ ] Manually reopen and inspect both projects from every run.
- [ ] Review evidence for exact versions, observed capabilities, restrictions, and sensitive data.
- [ ] Update only the matching matrix row after each evidence review.
- [ ] Confirm that no required matrix row remains `unverified` (`out-of-scope` is fine).
- [ ] Record any failed row's cause and accepted compatibility policy.
- [ ] Keep generated AEDT artifacts and raw evidence out of Git.
- [ ] Complete Task 11 only after all acceptance and gating rules above are satisfied.
