# Task 4: Optical Session and Binary Frame API

## Implementation

- Added `OpticalSession` with deterministic `from_file`, descriptor-safe `from_bytes`, and bounded binary frame production.
- Added per-app, in-memory optical sessions. Starting a session retains only the newest session.
- Added optical start, status, and binary frame routes.
- Optical start opens the incident through `IncidentStore.open_incident`, verifies the fixed artifact basename through `_open_verified_file`, reads that verified descriptor while it remains open, and closes it before building an in-memory session. It never reopens `FileArtifact.path`.
- Clip sessions accept `READY` and `ANALYSIS_FAILED`; report sessions accept only `READY`. Missing metadata artifacts return 404. Invalid state, metadata, integrity, symlink, and resolved-path failures return 409. Verified raw artifacts exceeding 16 MiB return 413 before container construction.
- Frame endpoints use `application/octet-stream` with `Cache-Control: no-store`, and reject negative or out-of-domain protocol identifiers with 404 rather than allowing packing errors.

## TDD evidence

### RED

Command:

```console
python3 -m pytest tests/test_optical_session.py tests/test_api.py::test_api_refuses_oversized_clip -q
```

Output:

```text
/opt/homebrew/opt/python@3.14/bin/python3.14: No module named pytest
```

The system `python3` has no pytest. The repository virtual environment was used to perform the requested RED/GREEN verification.

Command:

```console
.venv/bin/python -m pytest tests/test_optical_session.py tests/test_api.py::test_api_refuses_oversized_clip -q
```

Output:

```text
ERROR tests/test_optical_session.py
ModuleNotFoundError: No module named 'dashpi.optical.session'
1 error in 0.16s
```

After the session-only implementation, command:

```console
.venv/bin/python -W error -m pytest tests/test_optical_session.py tests/test_api.py::test_api_refuses_oversized_clip -q
```

Output:

```text
.....F
FAILED tests/test_api.py::test_api_refuses_oversized_clip - assert 405 == 413
1 failed, 5 passed in 0.15s
```

The remaining endpoint tests also failed before API implementation:

```console
.venv/bin/python -W error -m pytest tests/test_api.py -q -k optical
```

```text
FFFFFFFF
8 failed, 41 deselected in 0.18s
```

Each established the missing POST route (405) before the API implementation was written.

### GREEN

Command:

```console
.venv/bin/python -W error -m pytest tests/test_optical_session.py tests/test_api.py -q
```

Output:

```text
......................................................
54 passed in 0.35s
```

Focused brief command after implementation:

```console
.venv/bin/python -W error -m pytest tests/test_optical_session.py tests/test_api.py::test_api_refuses_oversized_clip -q
```

Output:

```text
......
6 passed in 0.12s
```

Full suite command:

```console
.venv/bin/python -W error -m pytest -q
```

Output:

```text
........................................................................ [ 33%]
........................................................................ [ 67%]
......................................................................   [100%]
214 passed in 6.51s
```

## Files

- `src/dashpi/optical/session.py`
- `src/dashpi/api.py`
- `tests/test_optical_session.py`
- `tests/test_api.py`

## Self-review

- Confirmed sessions are per-app and only the latest is reachable.
- Confirmed direct sessions deterministically repeat a sequence and `from_file` delegates to the bytes constructor.
- Confirmed API artifact reads use verified descriptor-relative access, retain the opened descriptor across a simulated path replacement, and do not invoke `Path.read_bytes` on metadata paths.
- Confirmed clip/report state gating, oversized raw-payload rejection, integrity/symlink rejection, binary content type, `no-store`, and invalid sequence/session domain responses.
- Ran `git diff --check`; no whitespace errors.

## Concerns

- The host `python3` does not include pytest; all executable verification used the repository's `.venv` interpreter.
- The session registry is intentionally process-local and only retains one session, as required; a server restart discards it.
