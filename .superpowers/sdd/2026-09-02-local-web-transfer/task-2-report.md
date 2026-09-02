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

## Fix Round 1

### Implementation

- The clip route now derives the only allowed artifact pathname as `store.directory(incident_id) / "clip.mp4"`. It rejects metadata whose `FileArtifact.path` does not exactly describe that incident-local contract.
- `range_response` now opens the canonical pathname once with `O_NOFOLLOW` where supported. It uses `lstat` plus `fstat` device/inode comparison, so a symlink or final-path replacement is also rejected on platforms without `O_NOFOLLOW`.
- The same opened descriptor is verified as a regular, nonempty file with the stored byte length and SHA-256, then sought and streamed. It is closed on validation/range errors and in a generator `finally` after streaming.
- Filesystem/open/integrity failures, including malformed digest metadata, become `409` before response headers or an ETag are made.

### Added regression coverage

- Valid digest/length metadata pointing to an outside path is rejected.
- An incident-local clip symlink to a content-identical external file is rejected.
- A test-only atomic replacement immediately after descriptor hashing proves the response retains the original descriptor's range body and ETag, rather than reopening the replacement pathname.
- Malformed persisted digest metadata is rejected as `409` without an ETag.

### RED

Command:

```console
.venv/bin/python -m pytest tests/test_api.py::test_clip_rejects_metadata_path_outside_incident tests/test_api.py::test_clip_rejects_symlink_even_when_target_matches_metadata tests/test_api.py::test_clip_streams_opened_descriptor_after_path_replacement -q -W error
```

Output before the fix:

```text
FFF
test_clip_rejects_metadata_path_outside_incident: expected 409, got 200
test_clip_rejects_symlink_even_when_target_matches_metadata: expected 409, got 200
test_clip_streams_opened_descriptor_after_path_replacement: expected original range bytes, got b'xxxxx'
3 failed in 0.15s
```

Command:

```console
.venv/bin/python -m pytest tests/test_api.py::test_clip_rejects_malformed_digest_metadata -q -W error
```

Output before malformed-metadata handling:

```text
F
TypeError: unsupported operand types(s) or combination of types: 'str' and 'NoneType'
1 failed in 0.26s
```

### GREEN

Command:

```console
.venv/bin/python -m pytest tests/test_ranges.py tests/test_api.py -q -W error
```

Output:

```text
21 passed in 0.18s
```

### Full suite

Command:

```console
.venv/bin/python -m pytest -q -W error
```

Output:

```text
78 passed in 4.60s
```

### Self-review

- No response is created until the canonical path's opened descriptor has passed all size/digest/file-type checks.
- The descriptor survives a pathname replacement, while the ETag and body remain tied to the verified original bytes.
- `lstat`/`fstat` identity matching supplements `O_NOFOLLOW` and rejects a symlink or changed final path without relying on metadata paths.
- The test synchronization hook performs a real atomic replacement and asserts endpoint output; it does not assert mock calls.

### Concerns

No blocking concerns. The existing per-request SHA-256 verification remains intentionally uncached.
