# Task 3 Report: Incident Windows and Overlapping Triggers

## Implementation

- Added `segments_for_window`, selecting segments with strict interval overlap (`segment.start_mono < end` and `segment.end_mono > start`).
- Added `IncidentCoordinator.trigger`, which creates collecting incidents and coalesces overlapping trigger windows while extending the existing post-trigger deadline to the later requested end.
- Added `IncidentCoordinator.ready_at`, returning active incidents whose state is collecting and whose deadline is at or before the supplied monotonic time.

## Files changed

- `src/dashpi/incidents.py`
- `tests/test_incidents.py`

## Self-review

- The implementation uses the existing `Settings`, `Segment`, `IncidentMetadata`, and `IncidentState` interfaces.
- Boundary behavior is covered: segments touching either window boundary are excluded.
- Trigger overlap and deadline extension are covered, as is readiness filtering by state and deadline.
- No persistence, media, camera, hotspot, browser, QR, cloud, account, native-app, or speculative abstraction work was added.
- `git diff --check` passed.

## Concerns

- `active` incidents remain in memory after becoming ready; this matches the requested offline in-memory coordinator scope. A later lifecycle owner can remove or transition them.
- The coordinator intentionally preserves the first incident's metadata when coalescing later triggers, while extending only its deadline as specified.

## TDD evidence

RED command:

```text
/Users/justin/Documents/ChatGPT/DashPi/.worktrees/dashpi-mvp/.venv/bin/python -m pytest tests/test_incidents.py -q
```

RED result: test collection failed with `ModuleNotFoundError: No module named 'dashpi.incidents'`, because the production module did not yet exist. This was the expected missing-implementation failure.

GREEN command:

```text
/Users/justin/Documents/ChatGPT/DashPi/.worktrees/dashpi-mvp/.venv/bin/python -m pytest tests/test_incidents.py -q && /Users/justin/Documents/ChatGPT/DashPi/.worktrees/dashpi-mvp/.venv/bin/python -m pytest -q
```

GREEN result: focused suite `4 passed in 0.01s`; full suite `13 passed in 0.01s`. The minimal implementation satisfies the supplied window, overlap-extension, and readiness behaviors.
