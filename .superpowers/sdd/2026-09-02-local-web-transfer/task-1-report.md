# Task 1 Report: Incident Listing Contract

## Implementation

- Added `IncidentStore.list()`, which loads only persisted incident metadata and orders it by `triggered_at` descending.
- Added `create_app(store)`, a local FastAPI factory with docs disabled and `GET /api/incidents`.
- The endpoint exposes the required metadata-only fields. It never returns artifact or storage paths, and completion flags come from metadata (`clip` and `report_html`), not directory contents.
- Added FastAPI/Uvicorn runtime dependencies and HTTPX in the development extra.

## Files

- Modified: `pyproject.toml`
- Modified: `src/dashpi/storage.py`
- Added: `src/dashpi/api.py`
- Added: `tests/test_api.py`

## TDD evidence

### RED

Required command:

```text
$ python3 -m pytest tests/test_api.py::test_list_returns_metadata_not_filesystem_paths -q
/opt/homebrew/opt/python@3.14/bin/python3.14: No module named pytest
```

The project venv provided the relevant dependency failure after the test was added:

```text
$ .venv/bin/python -m pytest tests/test_api.py::test_list_returns_metadata_not_filesystem_paths -q
E   ModuleNotFoundError: No module named 'fastapi'
1 error in 0.01s
```

### Dependency setup

```text
$ /Users/justin/.local/bin/uv pip install --python .venv/bin/python -e '.[dev]'
Resolved 22 packages; installed FastAPI 0.141.1, Uvicorn 0.52.4, HTTPX 0.28.1, and their transitive dependencies.
```

### GREEN

```text
$ .venv/bin/python -m pytest tests/test_api.py::test_list_returns_metadata_not_filesystem_paths -q
1 passed, 1 warning in 0.11s

$ .venv/bin/python -m pytest -q
58 passed, 1 warning in 4.47s
```

The warning originates in the installed FastAPI/Starlette `TestClient` import and is a third-party `StarletteDeprecationWarning` about its current HTTPX integration.

## Self-review

- Reviewed the public JSON shape against the brief; it contains exactly the seven required fields.
- Confirmed the endpoint constructs responses from `IncidentMetadata` rather than filesystem paths or scanned artifacts.
- `from __future__ import annotations` prevents the new `IncidentStore.list` method name from shadowing the built-in `list` in a later type annotation.
- Ran `git diff --check`; no whitespace errors.

## Concerns

- No functional concerns. The initial third-party warning is resolved in the follow-up below.

## Warning-resolution follow-up

The initial FastAPI/Starlette version selected by the declared ranges prefers `httpx2` for `TestClient`; the explicit `httpx` development dependency made Starlette use its deprecated fallback instead. The dev extra now uses `httpx2>=2,<3`, the current client package required by Starlette, and no longer declares `httpx` explicitly. This keeps `httpx` out of DashPi's direct dependency contract while preserving compatibility with FastAPI's test client.

### RED (warning as error)

```text
$ .venv/bin/python -m pytest tests/test_api.py::test_list_returns_metadata_not_filesystem_paths -q -W error
E   starlette.exceptions.StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
1 error in 0.09s
```

### Dependency refresh

```text
$ /Users/justin/.local/bin/uv pip install --python .venv/bin/python -e '.[dev]'
Resolved 22 packages; installed httpx2==2.12.0 and httpcore2==2.12.0.
```

### GREEN (warnings as errors)

```text
$ .venv/bin/python -m pytest tests/test_api.py::test_list_returns_metadata_not_filesystem_paths -q -W error
1 passed in 0.12s

$ .venv/bin/python -m pytest -q -W error
58 passed in 4.42s
```

## Fix Round 1: Exclude In-Progress Incidents

`IncidentStore.list()` now returns only terminal incident summaries: `READY`,
`CLIP_FAILED`, and `ANALYSIS_FAILED`. Because `GET /api/incidents` consumes
that method, it exposes the same completed/failed-only contract.

### Covering test

`tests/test_api.py::test_list_excludes_incidents_still_being_processed`

### RED

```text
$ .venv/bin/python -m pytest tests/test_api.py::test_list_excludes_incidents_still_being_processed -q -W error
F                                                                        [100%]
E       AssertionError: Left contains 3 more items, first extra item: <IncidentState.ANALYZING: 'analyzing'>
1 failed in 0.13s
```

### GREEN

```text
$ .venv/bin/python -m pytest tests/test_api.py::test_list_excludes_incidents_still_being_processed -q -W error
1 passed in 0.10s
```

### Full suite

```text
$ .venv/bin/python -m pytest -q -W error
59 passed in 4.48s
```

### Self-review

- The regression persists every defined state and confirms the three active states are excluded while all three terminal states remain, in descending trigger-time order.
- It asserts both `IncidentStore.list()` and the local API response, so moving or removing the filter from either consumer-visible boundary fails the test.
- `git diff --check` passed with no whitespace errors.
