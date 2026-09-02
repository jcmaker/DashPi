# Core Incident Pipeline Final Fix Report

## Scope

This wave changes only the core incident pipeline. No web, hotspot, or QR work
was changed.

## Findings resolved

### 1. Nonzero FFmpeg trim duration

`build_clip` now uses stream copy for zero-offset clips and a minimal
`libx264` video re-encode when a nonzero trim begins between keyframes. It
probes the partial output before fsync/hash/rename and rejects a nonzero trim
shorter than the requested duration by more than 0.1 seconds. The existing
`.partial` -> fsync -> SHA-256 -> rename ordering is retained.

Regression: `tests/test_media.py::test_nonzero_clip_offset_preserves_requested_duration`.

RED command and observed failure:

```text
.venv/bin/python -m pytest tests/test_media.py::test_nonzero_clip_offset_preserves_requested_duration -q
AssertionError: assert 2.9 <= 2.2
```

GREEN: `tests/test_media.py -q` -> `3 passed`.

### 2. Terminal incidents are not coalesced

`IncidentCoordinator.trigger` now considers only
`collecting_post_trigger` incidents when it checks for overlap. A READY
incident with an overlapping window therefore does not absorb a new trigger.

Regression: `tests/test_incidents.py::test_overlapping_trigger_after_terminal_incident_creates_new_incident`.

RED command and observed failure:

```text
.venv/bin/python -m pytest tests/test_incidents.py::test_overlapping_trigger_after_terminal_incident_creates_new_incident -q
AssertionError: assert 'inc-1' == 'inc-2'
```

GREEN: `tests/test_incidents.py -q` -> `6 passed`.

### 3. Ollama local-only trust boundary

`OllamaClient` accepts only an `http` numeric IPv4/IPv6 loopback origin. It
rejects credentials, paths other than `/`, queries, fragments, hostnames, and
non-loopback IPs. The proxy-disabled opener is retained and now includes a
redirect handler that refuses redirects, preventing a local request from
forwarding frame data elsewhere.

Regressions in `tests/test_reports.py` cover accepted/rejected origins, a real
local HTTP tags/generate exchange (request targets, timeouts, and payload),
and redirect refusal before the redirect target is requested.

RED command and observed failures:

```text
.venv/bin/python -m pytest tests/test_reports.py::test_client_rejects_non_loopback_or_non_origin_base_urls tests/test_reports.py::test_client_rejects_redirect_without_requesting_redirect_target -q
7 failures: Failed: DID NOT RAISE <class 'ValueError'>
redirect path reached urllib's default redirect handling rather than raising HTTPError(302)
```

An additional RED for a valid no-port numeric loopback origin was:

```text
.venv/bin/python -m pytest tests/test_reports.py::test_client_accepts_numeric_loopback_http_origins -q
ValueError: base_url must be a numeric loopback HTTP origin
```

GREEN: `tests/test_reports.py -q` -> `28 passed`.

### 4. Binding incident metadata and report contract

`IncidentMetadata` now records configured pre/post windows, clip duration,
and report model/generation time. Artifact metadata serialized into the
incident document includes filename, path, byte length, SHA-256, and duration
where applicable. The coordinator and CLI pass configured windows into new
metadata; the pipeline probes the completed clip and records report provenance
after both report artifacts are written. `IncidentStore` round-trips all of
these fields and supplies inexpensive defaults for metadata written before the
window fields existed.

HTML reports now visibly state the source clip digest, model, generation time,
and: “AI output is advisory and may be incomplete.” Observations and
limitations are HTML escaped.

Regressions:

- `tests/test_models.py::test_incident_metadata_includes_configured_windows_and_artifact_contract`
- `tests/test_storage.py::{test_store_round_trips_incident,test_store_loads_metadata_written_before_window_fields}`
- `tests/test_pipeline.py::test_pipeline_records_clip_and_report_metadata_from_configured_window`
- `tests/test_incidents.py::test_coordinator_records_configured_incident_window_durations`
- `tests/test_cli.py::test_cli_records_configured_window_durations_in_metadata`
- `tests/test_reports.py::test_html_identifies_report_provenance_and_escapes_hostile_lists`

RED failures included:

```text
IncidentMetadata.new() got an unexpected keyword argument 'pre_seconds'
loaded clip duration was None and older metadata could not construct IncidentMetadata
assert 'Source clip SHA-256: clip-digest' in rendered HTML
TypeError: '<=' not supported between float and NoneType for clip duration
assert (30.0, 7.0) == (12.0, 7.0) in coordinator metadata
assert (30.0, 2.0) == (2.0, 2.0) in CLI metadata
```

GREEN outputs:

```text
tests/test_models.py -q: 2 passed
tests/test_storage.py -q: 7 passed
tests/test_pipeline.py -q: 6 passed
tests/test_cli.py -q: 2 passed
```

## Deferred-review coverage

The storage round-trip test now compares complete serialized metadata,
including state, every transition, all artifacts, configured windows, clip
duration, and report provenance. Backward metadata defaults are covered.

`tests/test_pipeline.py` also reloads a persisted `analysis_failed` incident
after each of these failures and asserts that its clip remains available:

- frame sampling failure;
- invalid report validation; and
- report JSON write failure.

These three persistence tests passed immediately when added because the
existing analysis-failure transition/save path already provided that behavior;
they were retained as regression coverage and re-run in the focused suite.
The optional byte-length assertion was not otherwise touched.

## Verification

Focused amended suite:

```text
.venv/bin/python -m pytest tests/test_media.py tests/test_incidents.py tests/test_reports.py tests/test_models.py tests/test_storage.py tests/test_pipeline.py tests/test_cli.py -q
54 passed in 4.46s
```

Full suite:

```text
.venv/bin/python -m pytest -q
57 passed in 4.34s
```

CLI:

```text
.venv/bin/dashpi --help
usage: dashpi [-h] {simulate} ...
```

`git diff --check` exited successfully with no output.

## Files changed

- `src/dashpi/cli.py`
- `src/dashpi/incidents.py`
- `src/dashpi/media.py`
- `src/dashpi/models.py`
- `src/dashpi/pipeline.py`
- `src/dashpi/reports.py`
- `src/dashpi/storage.py`
- `tests/test_cli.py`
- `tests/test_incidents.py`
- `tests/test_media.py`
- `tests/test_models.py`
- `tests/test_pipeline.py`
- `tests/test_reports.py`
- `tests/test_storage.py`

## Self-review and concerns

The only intentional compatibility default is a 30-second pre-window and a
post-window derived from the older stored deadline and trigger timestamps.
There are no known remaining concerns in this scope. The nonzero clip check
uses a 0.1-second tolerance to account for container/frame timing precision;
the regression requests 3.0 seconds and verifies 2.9--3.1 seconds.
