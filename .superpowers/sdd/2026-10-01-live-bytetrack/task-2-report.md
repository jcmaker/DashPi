# Task 2 implementation report

## Changes

- `PiCameraRecorder` configures a 640×360 YUV420 lores stream only with a tracking model. Tracking starts after recording succeeds; its optional model/inference errors do not abort recording.
- One latest-frame worker captures, detects with the configured live confidence, and updates actual `LiveTracker` ByteTrack. A lock protects one replaceable result slot; no frame queue or extra camera exists.
- Nonblocking Picamera2 capture jobs use a signal callback to copy lores and release the request in `finally` before inference. Waiting polls every 50ms and times out after one second. Stop cancels pending camera jobs. Callback ownership releases even a job that completed between dequeue and cancellation.
- Recorder `stop()` and `release()` join the tracking worker before stopping/closing the camera, including DeviceSession tick/error paths. Stop clears results and each recording builds a new tracker.
- Existing Qt timer applies RGBA through the existing preview `set_overlay` on the main thread. Texture coordinates follow the camera image; 1-second stale results, stopped recording and release clear the overlay. Tracking errors append to the existing recording status, preserving incident/stop wording.
- Added CLI flags `--tracking-model`, `--tracking-fps` (10), `--tracking-confidence` (.10), `--tracking-activation` (.45), with finite/range validation.
- Parent's Pi validation identified supervision 0.27/SciPy 1.18 incompatibility (`splev` removed). Tracking extra now requires `scipy>=1.10,<1.18`; README documents flags and compatibility.

## RED/GREEN evidence

Initial runnable failing check: `.venv/bin/pytest tests/test_live_tracking.py -q` → **1 failed, 15 passed**. The slow-inference shutdown assertion failed with `ImportError: cannot import name TrackingWorker`, before worker implementation.

GREEN focused: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_live_tracking.py tests/test_pi_camera.py tests/test_desktop.py -q` → **85 passed in 27.57s**.

Checks cover slow inference stop/join with no stale result, inference failure without results, one camera across prepare→preview→start→tracking failure→split→stop, exact lores configuration, copied data and release before conversion, stalled capture cancellation before close, completion/cancel callback race release, Qt main-thread overlay application, stale clearing, and stop clearing. Existing focused baseline continues to pass.

Full suite attempt via `.venv/bin/pytest -q` hit an existing invocation issue (repository `tests` namespace not importable from the executable entry point). Using Python's module invocation resolves it without repository changes:
`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` → **492 passed, 14 existing FastAPI deprecation warnings, 74.72s**. Final full run after the two last regression checks is recorded below.

`git diff --check` → clean.

## Self-review and concerns

Reviewed all recorder start/stop/release paths, DeviceSession automatic/error stops, and Qt async job polling. Recording output and incident pipeline are untouched. Capture cancellation cancels Picamera2's pending jobs; this application's encoder/split output operations are not Picamera2 capture jobs. Use of cancellation during a camera timeout is consistent with Picamera2's documented recovery API.

A completion callback may run after the waiting worker abandons a dequeued job; it always releases its request and skips copying when stop is set. No inference/thread or stale result can cross into a new session. Hardware restart/close behavior and overlay image alignment still require the parent's actual Pi validation, especially this uncommon cancellation race.

Worker shutdown deliberately waits for an in-progress synchronous OpenCV inference to finish; this protects ownership rather than abandoning a thread. A permanently hung native detector could therefore delay shutdown. The failed-camera capture path itself has a bounded wait.

No physical Pi tests were performed by this implementation agent; parent owns those operations.

Final full suite: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` → **494 passed, 14 existing warnings, 71.71s**.

## Fix round 1 (review findings)

Addressed all four Important findings and constructor validation:

- Replaced transferred-request callbacks with verified native `capture_array("lores", wait=False)`. Picamera2 copies/release under its camera lock before dequeue; polling and cancellation now deal only with owned arrays. Removed manual callback lifetime machinery and its late-request shutdown concern.
- Overlay clearing skips a closed camera and resets visibility in `finally`. Exceptions from render/apply/clear are contained, report tracking failure while preserving current status text, and signal only the tracking worker to stop. Failed overlay processing stays disabled until a new recording.
- CLI, recorder and worker enforce finite FPS in `(0,10]`; recorder also validates confidence/activation ranges at its public constructor.
- Regression checks enforce the native capture-array contract, late array signal after camera close without retained requests, closed-preview contract, optional overlay failure, status preservation, and invalid runtime values.

RED: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_pi_camera.py tests/test_live_tracking.py tests/test_desktop.py -q` → **17 failed, 82 passed in 29.79s**, before these production fixes (capture API, missing validation, escaped closed-camera/apply errors).

GREEN: same focused command → **99 passed in 28.31s**. Existing fake-MP4 demux diagnostics remain expected in GUI fixtures.

`git diff --check` → clean. Self-review confirms native capture-array ownership eliminates the prior late request-release hazard; recorder shutdown still joins a running synchronous inference as documented. No Pi operations performed.
