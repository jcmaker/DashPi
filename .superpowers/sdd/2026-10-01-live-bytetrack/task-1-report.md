# Task 1 implementation report

Status: DONE_WITH_CONCERNS (Pi compatibility remains a deployment verification).

## Changes

- `src/dashpi/live_tracking.py`: lazy supervision import at construction, finite positive frame rate and (0, 1) activation threshold validation; actual public supervision ByteTrack/Detections API, one tracker per ROAD_USERS class, COCO-based disjoint visible IDs; empty updates age every tracker. Retains original label/confidence/box values through supervision source indices. Deterministic RGB colors and transparent uint8 RGBA boxes/labels with clipping.
- `tests/test_live_tracking.py`: real ByteTrack behavioral tests for the exact required high/high/low sequence, ID isolation/continuity, empty-frame expiry, low-confidence nonactivation, class filtering, constructor validation, transparent overlay coordinates/bounds, color stability and fresh-process optional dependency absence.
- `pyproject.toml`: optional `tracking = ["supervision==0.27.0", "opencv-python>=4.12,<5"]`; existing base dependencies unchanged. Optional OpenCV bound keeps supervision's transitive cv2 wheel in the same supported major for regular pip installations.
- `README.md`: optional installation, supported YOLOv8n COCO ONNX input/output and explicit model path, 0.10 live detector input, 0.45 activation, 10Hz target, new-track threshold detail, coordinate contract and preview-only behavior. Existing detector behavior unchanged.

## Dependency/API verification

Installed with `.venv/bin/python -m pip install 'supervision==0.27.0'` (success). Read the installed public ByteTrack signature and update implementation: track_activation_threshold, frame_rate, update_with_detections; empty detections advance frame counter. Default library lost-track buffer is 30, scaled to 10 frames at our default frame rate. ByteTrack's own new-track confidence threshold is activation + 0.10; this behavior is documented, not overridden.

Actual verified local versions: Python 3.11.15, NumPy 2.4.6, supervision 0.27.0, OpenCV 4.14.0. Installed supervision initially resolved opencv-python 5.0; local wheel was brought within the project's existing OpenCV major bound using `.venv/bin/python -m pip install 'opencv-python>=4.12,<5'` (success).

## RED / GREEN evidence

1. Wrote the behavioral tests before creating the implementation.
2. RED: `.venv/bin/python -m pytest tests/test_live_tracking.py -q` → exit 2, one collection error `ModuleNotFoundError: No module named 'dashpi.live_tracking'`.
3. Initial GREEN after minimum implementation: same command → exit 0, **14 passed in 0.58s**.
4. Added subprocess optional-dependency absence check; first run found a test harness issue (subprocess lacked pytest's src path), **1 failed / 14 passed**. Supplied the parent's import path, preserving a fresh process that blocks supervision import; no ByteTrack mock.
5. Final GREEN: `.venv/bin/python -m pytest tests/test_live_tracking.py -q` → exit 0, **15 passed in 0.50s**.
6. Regression: `.venv/bin/python -m pytest tests/test_vision.py -q` → exit 0, **5 passed in 0.12s**.
7. Combined: `.venv/bin/python -m pytest tests/test_live_tracking.py tests/test_vision.py -q` → exit 0, **20 passed in 0.55s**.
8. `git diff --check` → exit 0, no output.

## Self-review

No association algorithm was implemented locally. No base dependency, detector default, camera, recording, or raw media path was changed. Each class updates even for empty detections; arithmetic visible ID namespaces avoid a growing ID translation map. The subprocess test verifies both core/module imports and overlay rendering without supervision, with a clear error only when tracking is requested. Overlay coordinates are explicitly in the requested overlay space; scaling belongs to the later camera integration. No Pi operations were performed.

## Concerns / limits

- Local macOS Python/NumPy compatibility has been exercised; actual Debian Pi Python/apt NumPy compatibility remains Task 3. The task explicitly prohibited Pi operations.
- supervision's metadata brings `opencv-python` in addition to DashPi's `opencv-python-headless`. Its transitive wheels must be handled carefully in the Pi system-site-packages environment to preserve apt Picamera2/OpenCV; README explains this. No Pi install command was executed.
- Camera worker/Qt overlay installation, stale result clearing, error display, session lifecycle and performance are later tasks, not implemented here.
- Tracker input is the existing detector's valid xyxy dictionary contract. Renderer clipping is verified, but callers must map coordinates when overlay dimensions differ.
