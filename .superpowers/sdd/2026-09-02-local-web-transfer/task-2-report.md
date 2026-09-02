# Task 2 report — safe single-range clip streaming

## Implementation

- Added `dashpi.ranges.parse_range` for one RFC-style byte range: closed, open-ended, and suffix forms. Missing headers select a full response; malformed, multi-range, reversed, and out-of-file ranges are rejected.
- Added bounded 1 MiB file streaming through `range_response`. It returns `200` for the full artifact and `206` with `Content-Range` for a selected range, and includes `Accept-Ranges`, `Content-Length`, and a SHA-256 ETag.
- Added `GET /api/incidents/{incident_id}/clip`. The endpoint supplies only its validated incident ID to `IncidentStore.load`; it never accepts or derives a filename/path from request input.
- Before any full or ranged response is created, the endpoint verifies that the `FileArtifact` is a regular existing file, has a positive recorded length, matches the current byte length, and has the recorded SHA-256 digest. Invalid artifacts receive `409` before an ETag or streaming response is created.

## Files

- Created `src/dashpi/ranges.py`
- Modified `src/dashpi/api.py`
- Created `tests/test_ranges.py`
- Modified `tests/test_api.py`

## TDD evidence

### RED

Command:

```console
.venv/bin/python -m pytest tests/test_ranges.py tests/test_api.py::test_clip_supports_resume_and_hash -q
```

Output (expected failure before production implementation):

```text
ERROR tests/test_ranges.py
ModuleNotFoundError: No module named 'dashpi.ranges'
1 error in 0.22s
```

The test suite failed because the requested parser/streaming module did not exist.

### GREEN

Command:

```console
.venv/bin/python -m pytest tests/test_ranges.py tests/test_api.py -q -W error
```

Output:

```text
17 passed in 0.15s
```

The focused API tests exercise a real `IncidentStore` and on-disk clip. They cover resumed delivery and digest ETag, invalid IDs, and each invalid-artifact condition for both full and ranged requests: missing file, zero length, byte-length mismatch, and same-length digest mismatch. Every invalid case asserts `409` and no ETag.

### Full suite

Command:

```console
.venv/bin/python -m pytest -q -W error
```

Output:

```text
74 passed in 4.47s
```

### Diff hygiene

Command:

```console
git diff --check
```

Output: no output (success).

## Self-review

- The route receives an incident ID only; `IncidentStore.directory` rejects traversal-shaped or invalid IDs before any path is resolved.
- `FileArtifact.byte_length` and `FileArtifact.sha256` are checked against the actual file before `range_response` can build `200`/`206` headers, so corrupted data cannot carry a stale ETag.
- Only a single byte range is accepted; comma-separated multi-ranges are rejected with `416` by the response helper.
- Streaming reads no more than 1 MiB per iteration and closes the file through the generator context manager.

## Concerns

No blocking concerns. Integrity validation deliberately hashes the artifact for each download request; this is the smallest safe implementation required for this slice and is intentionally not cached.
