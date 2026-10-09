# Live ByteTrack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task.

**Goal:** Show live tracked road objects on the Pi LCD during recording.
**Architecture:** Reuse OpenCV YOLOv8n detector, supervision ByteTrack, a single latest-frame worker and Picamera2 RGBA preview overlay.
**Tech Stack:** Python, OpenCV, supervision, Picamera2, PySide6.

## Global Constraints

- Internet 없이 감지·추적한다. 원본 MP4에는 박스를 넣지 않는다.
- 카메라를 한 번만 열고 기존 녹화·사고 보존을 유지한다.
- 대상은 person, bicycle, car, motorcycle, bus, truck이다.
- low confidence 0.10, activation 0.45, maximum inference 10Hz, stale overlay timeout 1 second; expose tuning knobs.
- Class-specific ByteTrack instances, session-unique visible IDs, deterministic color per ID.
- Native deployment target: /home/wonmaker/DashPi-native, SSH alias wonmaker.
- Keep changes minimal, no Torch dependency on Pi, no new screen layout.

### Task 1: Tracking engine and optional dependency

**Files:** Create src/dashpi/live_tracking.py, tests/test_live_tracking.py; modify pyproject.toml and README.md.
**Interfaces:** LiveTracker(frame_rate=10, activation_threshold=0.45).update(detections: list[dict]) -> list[dict] retaining label/confidence/box/track_id. track_color(track_id) returns RGB tuple. render_overlay(width, height, detections) returns uint8 RGBA array. Later worker consumes these interfaces.

- [ ] Verify supervision version compatibility and install locally, pin supported version in optional `tracking` extra without changing existing base dependencies. Keep imports lazy so core remains usable without supervision.
- [ ] Write a real ByteTrack behavioral test before implementation:
```python
def test_low_confidence_keeps_existing_id():
    tracker = LiveTracker()
    first = tracker.update([dict(label='car', confidence=.9, box=[10,10,70,70])])
    second = tracker.update([dict(label='car', confidence=.9, box=[11,10,71,70])])
    low = tracker.update([dict(label='car', confidence=.2, box=[12,10,72,70])])
    assert first[0]['track_id'] == second[0]['track_id'] == low[0]['track_id']
```
Also check separate classes never share visible IDs, empty frames advance tracker, colors repeat and transparent overlay bounds map correctly. Do not mock ByteTrack.
- [ ] Run `.venv/bin/python -m pytest tests/test_live_tracking.py -q` expecting RED, implement minimum engine then GREEN. Constructor validates finite positive frame rate and thresholds. Reuse ROAD_USERS and COCO labels; use installed supervision API, no custom association algorithm.
- [ ] Document optional installation, model format/path, thresholds and preview-only behavior. Run tests/test_vision.py as regression. Commit and report test evidence.

### Task 2: Latest-frame worker, camera and Qt integration

**Files:** Modify src/dashpi/live_tracking.py, src/dashpi/pi_camera.py, src/dashpi/desktop.py, README.md; test tests/test_live_tracking.py, tests/test_pi_camera.py and tests/test_desktop.py.
**Consumes:** Task 1 LiveTracker/update and render_overlay.
**Produces:** Explicit CLI flags `--tracking-model PATH`, `--tracking-fps` (10), `--tracking-confidence` (.10), `--tracking-activation` (.45). Tracking disabled if no model specified; model errors disable only tracking.

- [ ] Read all camera start/stop/release callers and existing Qt timer/polling before modifying. Create fail-first checks for single camera ownership, copied/released lores request, worker bounded results, failure and shutdown.
- [ ] Add lores 640x360 YUV420 only when tracking enabled. Provide read_tracking_frame() which captures one request, copies lores data, releases request in finally, converts with COLOR_YUV2BGR_I420. Do not hold camera requests during inference.
- [ ] Use one worker thread, stop Event, one result slot under lock. Capture and infer latest frames with no queued frames. YoloDetector uses live confidence; main thread polls results using Qt timer, updates transparent set_overlay; clear results over 1 second old. Return image shape/boxes consistently so overlay fills preview correctly.
- [ ] Start tracking only after recording succeeds. Stop before camera stop/release; avoid requests racing camera close, clear overlay and reset tracker each session. Failure or missing model is reported in existing status area without aborting recording. Preserve incident and stop status messages. Lazy imports keep fake camera and no-tracking tests working.
- [ ] Runnable acceptance pattern:
```python
# Existing fake camera recorder: prepare -> preview -> start -> tracking failure -> split -> stop.
# Assert camera created once, split yields segment, stop closes once, no worker survives release.
# Worker with slow detector: stop waits safely for request release and no stale result crosses sessions.
```
Implement these as focused real assertions using existing fake camera fixture, plus test GUI overlay is cleared on stop and stale output. Run focused tests and full Python suite once; commit report.

### Task 3: Pi deployment and hardware acceptance

**Files:** Create docs/live-bytetrack-pi-acceptance.md; modify README only if installation findings require it.
**Consumes:** Task 2 CLI and native camera integration.

- [ ] Inspect actual app process data root, launcher, display environment, git status. Preserve existing recordings, settings and API secrets. Backup changed native source files before deployment; install pinned tracking dependency without replacing Pi apt NumPy/OpenCV packages. Do not dump secrets.
- [ ] Prepare supported YOLOv8n COCO ONNX model using workstation export or verified download; validate OpenCV accepts output; copy to persistent Pi models directory. No runtime downloads.
- [ ] Deploy reviewed source files to native checkout. Gracefully stop existing GUI app, start test app on actual display with separate acceptance data root; measure live tracking and MP4 simultaneously, ffprobe segments. Capture screenshot or preview artifact to inspect boxes; confirm real captured objects and stable ID if scene provides them.
- [ ] Measure detector FPS, preview/camera frame delivery, CPU, RSS, temperature; stop and repeat recording once. Check no stuck worker, valid MP4, no altered production evidence. Restart regular launcher with tracking enabled using explicit model path after successful validation. Record commands, values, limitations and rollback in acceptance document; commit documentation.
