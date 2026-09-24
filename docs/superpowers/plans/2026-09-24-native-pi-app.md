# Native Raspberry Pi App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Execute inline and commit each tested task.

**Goal:** A Raspberry Pi 5 desktop icon opens a native DashPi app with camera preview, recording, manual incident analysis, records, settings, and optical report transfer.

**Architecture:** Picamera2 alone owns the camera, supplying a PySide6 preview and timestamped MP4 segments. A small session controller reuses the current incident coordinator, pipeline, store, and worker. Qt dispatches actions and shows state; it never waits for camera, FFmpeg, or Ollama work.

**Tech Stack:** Python 3.11+, PySide6 6.7.3, Picamera2 (`QGlSide6Picamera2`, `LibavH264Encoder`, `SplittableOutput`, `PyavOutput`), FFmpeg, Ollama, `qrcode`.

## Global Constraints

- Pi 5, LCD, camera only; no microphone, GPS, speed, battery, ignition, or physical trigger features.
- Recording page: live video and exactly two controls below it: `사고 분석`, `종료`.
- Manual trigger preserves 30 seconds before and collects 15 seconds after; recording continues. `종료` during that window stops only once collection completes.
- Camera failure before the deadline cannot create a supposedly complete clip; leave raw footage intact. AI failure must leave the evidence clip available.
- No Chromium, Electron, QML, web view, or FastAPI server in the native app path.
- Keep current synthetic/rpicam tests passing; actual Pi performance, timing, and simultaneous preview/recording remain hardware acceptance gates.

## File Map

- `src/dashpi/pi_camera.py`: Picamera2 owner and timestamped MP4 segmentation. Import Pi-only modules lazily.
- `src/dashpi/device_session.py`: incident trigger, pending stop, retention, and pipeline dispatch.
- `src/dashpi/desktop.py`: Qt Widgets screens, preview, playback, settings, and QR animation.
- `src/dashpi/desktop_install.py`: desktop entry and icon installation.
- `src/dashpi/device.py`: existing settings and tested rpicam prototype; reuse, do not rewrite.
- `pyproject.toml`, `README.md`: optional dependencies, entry points, Pi install and acceptance instructions.
- `tests/test_pi_camera.py`, `tests/test_device_session.py`, `tests/test_desktop.py`, `tests/test_desktop_install.py`: fake-camera and offscreen Qt checks.

**Implementation checkpoint (2026-09-24):** The four software tasks were implemented in `60fd7d3`, `7bf2775`, `53f2b41`, and `3511b7a`; safety follow-up is `a1bdfe6`. The session exposes the few attributes the UI reads directly instead of adding an unused status-snapshot abstraction. Normal/parking recordings are playable by MP4 segment; incident evidence is a single `clip.mp4`. The Raspberry Pi 5 acceptance gate below is still open—desktop tests cannot validate camera timing, codec support, or performance. The checkboxes remain the original execution recipe, not a claim of Pi acceptance.

**Review follow-up (2026-09-24):** `1e15005` prevents MP4 filename reuse after pruning, rejects pre-capture triggers, waits for post-window frame coverage, and releases a failed startup for retry. `5430327` makes segmented playback continuous, prepares verified media/QR data off the Qt thread, shows disk usage, and tolerates an unreadable empty tail after a protected incident boundary. A further follow-up guards close/double-tap and settings errors during startup, keeps verified clips across QR navigation, and makes failure exit possible. The latest desktop suite passed 359 tests; Pi hardware acceptance remains open.

---

### Task 1: One camera, live-preview-compatible MP4 segments

**Files:** Create `src/dashpi/pi_camera.py`, `tests/test_pi_camera.py`.

**Interfaces:** `PiCameraRecorder(root: Path, settings: VideoSettings, segment_seconds: float = 2.0)` exposes `prepare() -> None`, `start(mode: str)`, `split() -> list[Segment]`, `stop() -> list[Segment]`, `segments`, `recording`, and `picam2`. Call `prepare()` in a worker, then embed `QGlSide6Picamera2(recorder.picam2)` on the Qt thread, then call `start()` in the worker. Attaching after `start_recording()` is not safe because Picamera2 starts its null preview loop first.

- [ ] **Step 1: Write failing fake-backend tests.** Inject fake Picamera2/encoder/output classes at the lazy import boundary. Check one camera construction, one recording start, two closed MP4 segments with contiguous time ranges after `split()`/`stop()`, and an actionable error when required Picamera2 APIs are missing.

```python
def test_single_camera_and_two_closed_segments(fake_picamera2, tmp_path):
    from dashpi.device import VideoSettings
    from dashpi.pi_camera import PiCameraRecorder
    recorder = PiCameraRecorder(tmp_path, VideoSettings())
    recorder.prepare()
    recorder.start("drive")
    assert len(recorder.split()) == 1
    result = recorder.stop()
    assert fake_picamera2.created == 1
    assert len(result) == 2
    assert result[0].end_mono == result[1].start_mono
    assert all(segment.path.exists() for segment in result)
```

- [ ] **Step 2: Run red.** `PYTHONPATH=src:. .venv/bin/pytest -q tests/test_pi_camera.py`; expect missing module.
- [ ] **Step 3: Implement.** `prepare()` constructs/configures one camera with video `main` at selected resolution and `FrameRate` at selected FPS. After Qt attaches its preview, `start()` uses `LibavH264Encoder(bitrate=bitrate_mbps * 1_000_000, iperiod=fps * 2, framerate=fps)`, `SplittableOutput(PyavOutput(first_mp4))`, and `picam2.start_recording`. In a worker, call `split_output(PyavOutput(next_mp4))`; after it returns, `probe_duration` the closed file and append `Segment`. On stop, close the last output before probing. Persist `session.json` and `segments.csv` through `atomic_write`. Use a monotonic first-capture anchor. Report absent Picamera2 APIs clearly before camera start.
- [ ] **Step 4: Run green and commit.** `PYTHONPATH=src:. .venv/bin/pytest -q tests/test_pi_camera.py tests/test_device.py`; then `git add src/dashpi/pi_camera.py tests/test_pi_camera.py && git commit -m 'feat: add single-owner Picamera2 recording path'`.

### Task 2: Manual trigger, protected history, delayed stop

**Files:** Create `src/dashpi/device_session.py`, `tests/test_device_session.py`; reuse `incidents.py`, `pipeline.py`, `storage.py`, `analysis_worker.py`.

**Interfaces:** `DeviceSession(recorder, settings: Settings, store: IncidentStore, worker: AnalysisWorker, analyze: Callable, detector=None)` exposes `start(mode)`, `trigger(now: float) -> IncidentMetadata`, `stop(now: float) -> bool` (`False` = pending), `tick(now: float)`, `pending_stop`, and a read-only status snapshot. `tick` runs on a worker, not the Qt thread.

- [ ] **Step 1: Write failing tests** with a fake recorder and `Settings(tmp_path, "fake", pre_seconds=30, post_seconds=15)`: trigger at 100, stop at 101, still record at 114.9, stop after 115; capture failure at 110 leaves raw segments and marks `clip_failed`; pruning never removes protected segments or saved incident clips.

```python
def test_stop_waits_for_post_window(session, fake_recorder):
    session.start("drive")
    session.trigger(100.0)
    assert session.stop(101.0) is False
    session.tick(114.9)
    assert fake_recorder.recording
    session.tick(115.0)
    assert not fake_recorder.recording
```

- [ ] **Step 2: Run red.** `PYTHONPATH=src:. .venv/bin/pytest -q tests/test_device_session.py`; expect missing module.
- [ ] **Step 3: Implement.** Use `IncidentCoordinator.trigger`/`ready_at`, `segments_for_window`, and `AnalysisWorker.submit(lambda: IncidentPipeline(...).process(...))`. At the deadline, close the current segment before pipeline submission. Keep all segments needed by collecting incidents; prune oldest unprotected raw MP4 using existing `bytes_to_free` and `choose_prunable_segments`. Persist an incomplete-capture `clip_failed` record when capture stops early, without deleting raw files. A pending stop finishes only after all post windows end.
- [ ] **Step 4: Run green and commit.** `PYTHONPATH=src:. .venv/bin/pytest -q tests/test_device_session.py tests/test_incidents.py tests/test_pipeline.py tests/test_storage.py`; then commit the two new files as `feat: coordinate manual incident capture and delayed stop`.

### Task 3: Native window, records, playback, settings

**Files:** Create `src/dashpi/desktop.py`, `tests/test_desktop.py`; modify `pyproject.toml`.

**Interfaces:** `DashPiWindow(session, store: IncidentStore, settings_path: Path)` is a `QMainWindow`. `main()` starts `QApplication`. The window reads session state and dispatches commands; worker completion reaches Qt via signals or timer polling, never direct cross-thread widget mutation.

- [ ] **Step 1: Write failing offscreen tests** for home buttons `녹화기록`, `주행시작`, `설정`; drive/parking confirmation; exactly `사고 분석` and `종료` below preview; pending-stop text; normal/event/parking list filters; native MP4 playback; persisted supported settings. Assert no mic/GPS/battery controls.

```python
def test_recording_controls_are_exactly_two(qapp, session, store, tmp_path):
    from dashpi.desktop import DashPiWindow
    window = DashPiWindow(session, store, tmp_path / "settings.json")
    window.show_recording()
    assert [button.text() for button in window.recording_controls()] == ["사고 분석", "종료"]
```

- [ ] **Step 2: Run red.** `QT_QPA_PLATFORM=offscreen PYTHONPATH=src:. .venv/bin/pytest -q tests/test_desktop.py`; expect missing module.
- [ ] **Step 3: Implement.** Use `QStackedWidget`, layouts, labels, large buttons, combo boxes, `QGlSide6Picamera2(session.recorder.picam2)`, and `QMediaPlayer`/`QVideoWidget`. Create the camera in a worker, attach the widget on the Qt thread, then start recording in the worker. Render verified report JSON as native text; keep the MP4 available on `analysis_failed`. Save `VideoSettings` with existing `save_settings`; apply capture changes only at next recording. Camera start/split/stop and AI remain off the Qt UI thread. Add `dashpi-app = "dashpi.desktop:main"` and a `pi` optional-dependency group with PySide6 and `qrcode`.
- [ ] **Step 4: Run green and commit.** `QT_QPA_PLATFORM=offscreen PYTHONPATH=src:. .venv/bin/pytest -q tests/test_desktop.py tests/test_device_session.py`; commit task files as `feat: add native DashPi controls and records`.

### Task 4: Optical QR, desktop launcher, and handoff

**Files:** Modify `src/dashpi/desktop.py`, `pyproject.toml`, `README.md`; create `src/dashpi/desktop_install.py`, `tests/test_desktop_install.py`; extend `tests/test_desktop.py`.

**Interfaces:** `OpticalSession.from_file(path, "text/html", block_size=512, session_id=...)`; `frame(sequence) -> bytes`. `install_launcher(applications_dir: Path, desktop_dir: Path, executable: Path)` writes an icon and a `.desktop` entry to those exact destinations.

- [ ] **Step 1: Write failing checks**: verify `report.html` bytes and SHA-256 before optical start; a file over `MAX_PAYLOAD` shows unavailable; the existing `FountainDecoder`/`unpack_container` recovers frame bytes; launcher has `Type=Application`, absolute `Exec`, and `Terminal=false`.
- [ ] **Step 2: Run red.** `QT_QPA_PLATFORM=offscreen PYTHONPATH=src:. .venv/bin/pytest -q tests/test_desktop.py tests/test_desktop_install.py`; expect missing behavior.
- [ ] **Step 3: Implement.** Use `IncidentStore.open_incident` and `_open_verified_file` for the report. Encode each optical frame with `qrcode`, show it in a `QLabel`, advance using `QTimer`, and warn that compatible cameras can capture the transfer. Install a packaged SVG and desktop entry pointing at `dashpi-app`, not Chromium. Document Pi OS 64-bit, `python3-picamera2`, FFmpeg, Ollama/model, install/run commands, and unverified-on-hardware status.
- [ ] **Step 4: Verify and commit.** `PYTHONPATH=src:. .venv/bin/pytest -q`; `QT_QPA_PLATFORM=offscreen PYTHONPATH=src:. .venv/bin/pytest -q tests/test_desktop.py`; `git diff --check`; package-install smoke test. Commit task files as `feat: add optical report display and Pi launcher`.

## Raspberry Pi 5 Acceptance Gate

On the connected LCD and camera, confirm one Picamera2 instance previews while producing playable MP4 segments. Measure button press versus evidence-frame timing, the 30/15-second clip window, delayed stop, cold launch, idle/capture/analysis memory, button response, sustained temperature, low-storage behavior, and phone PWA QR decoding. Verify power-loss recovery on a sacrificial session. If 1080p30 software encoding stalls or swaps, use the existing 720p/24 FPS settings and repeat before changing UI technology.
