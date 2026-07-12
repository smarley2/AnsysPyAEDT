# Agent Instructions

This repository is developed by people and multiple coding agents. These rules apply to every change made by Codex or another compatible agent.

## Read before editing

1. Read `docs/superpowers/specs/2026-07-12-pyaedt-inductor-application-design.md`.
2. Read `docs/architecture/README.md`.
3. Read the active plan under `docs/superpowers/plans/` when one exists.
4. Check `git status` and preserve unrelated or uncommitted work.

## Non-negotiable rules

- Use English for code, schemas, documentation, UI copy, logs, branches, commits, and pull requests.
- Keep `domain`, `geometry`, `materials`, and solver-independent simulation recipes free of imports from PyAEDT, Qt, SQLite, or operating-system APIs.
- Put AEDT and PyAEDT version differences behind adapter interfaces.
- Never change a physical assumption, schema, catalog value, unit, source reference, or approximation silently.
- Add or update tests before implementing a feature or bug fix.
- Do not edit generated catalog indexes manually. Edit canonical YAML, JSON, or CSV sources and rebuild the index.
- Do not commit copyrighted datasheets, screenshots, AEDT projects, generated solver output, credentials, or license files unless their redistribution is explicitly allowed.
- Record significant architectural changes in `docs/adr/`.
- Run the verification commands required by the active plan before claiming completion.

## Collaboration

- Codex branches use `codex/<task>`.
- Claude branches use `claude/<task>`.
- Do not run Codex and Claude concurrently in the same working tree.
- Each task must identify its owner, allowed files, dependencies, acceptance criteria, and verification commands.
- Hand off with a clean summary of changed files, remaining risks, and exact test results.
- Prefer small, reviewable commits and avoid unrelated refactors.

When these instructions conflict with an approved specification or plan, stop and request a documented decision rather than guessing.
