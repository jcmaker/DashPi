# Task 2 Report: Atomic Incident Storage and Retention Selection

## Implementation

- Added `sha256_file` for streaming SHA-256 calculation.
- Added `atomic_write`: writes `.partial`, flushes and fsyncs, hashes the complete partial, then atomically renames it and returns `FileArtifact`.
- Added `IncidentStore` metadata save/load round-trip, incident-ID path validation, and stale partial cleanup that preserves active partials.
- Added pure `bytes_to_free` pressure calculation and chronological `choose_prunable_segments` with protected-segment exclusion.

## Files changed

- `src/dashpi/storage.py`
- `tests/test_storage.py`

## TDD evidence

RED command:
`/Users/justin/Documents/ChatGPT/DashPi/.worktrees/dashpi-mvp/.venv/bin/python -m pytest tests/test_storage.py -q`

RED result: collection failed with `ModuleNotFoundError: No module named 'dashpi.storage'` (expected before implementation).

GREEN command:
`.../.venv/bin/python -m pytest tests/test_storage.py -q && .../.venv/bin/python -m pytest -q`

GREEN result: focused `5 passed`; full suite `8 passed`.

## Self-review and concerns

- `git diff --check` passed; implementation is limited to the requested storage and tests.
- Completed clips are not selected by retention when their paths are in `protected`.
- No concerns identified within the requested scope. Directory fsync after rename is not added because the brief specifies the tested minimal implementation.

## Hygiene follow-up

- Added `__pycache__/`, `*.py[cod]`, and `.pytest_cache/` to the existing `.gitignore`.
- Removed the generated untracked cache files under `src/dashpi/__pycache__/` and `tests/__pycache__/`.
- No production or test behavior changed; tests were intentionally not rerun.

Command output:

    $ git status --short
     M .gitignore
     M .superpowers/sdd/2026-09-02-core-incident-pipeline/task-2-report.md

    $ git diff --check
    (no output; passed)

## Fix Round 1

- Added `test_retention_selects_nothing_without_pressure` to `tests/test_storage.py`.
- RED command: `/Users/justin/Documents/ChatGPT/DashPi/.worktrees/dashpi-mvp/.venv/bin/python -m pytest tests/test_storage.py::test_retention_selects_nothing_without_pressure -q`
- RED result: `1 failed`; zero pressure incorrectly returned the unprotected segment.
- Added the minimal `if bytes_to_free <= 0: return []` guard in `src/dashpi/storage.py`.
- GREEN/focused command: `/Users/justin/Documents/ChatGPT/DashPi/.worktrees/dashpi-mvp/.venv/bin/python -m pytest tests/test_storage.py -q`
- GREEN/focused result: `6 passed in 0.01s`.
- Full command: `/Users/justin/Documents/ChatGPT/DashPi/.worktrees/dashpi-mvp/.venv/bin/python -m pytest -q`
- Full result: `9 passed in 0.01s`.
