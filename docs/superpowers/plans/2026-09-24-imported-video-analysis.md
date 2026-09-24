# Imported Video Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Play the transferred MP4 from native records, analyze at the chosen playback position, show the QR report, and launch full-screen without a desktop confirmation.

**Architecture:** Scan `~/Videos` in the Qt records view, reusing the detail player. Submit an offline incident job to the existing analysis worker and store; on completion use the existing optical page. Keep the PCManFM fix scoped to the DashPi launcher where possible.

**Tech Stack:** Python 3.11+, PySide6 Qt Widgets/Multimedia, FFmpeg, Ollama, pytest, Raspberry Pi OS PCManFM.

## Global Constraints

- Preserve the source MP4 and existing Pi `~/DashPi` data.
- The trigger is the current playback position; use at most 30 seconds before and 15 seconds after, clamped to available footage.
- Analysis/QR work must not block Qt; preserve a failed evidence clip.
- The launcher must be full-screen and free of click confirmation; do not disable PCManFM confirmation for every script unless a scoped fix is impossible.

---

### Task 1: Imported video records and playback

**Files:** Modify `src/dashpi/desktop.py`; test `tests/test_desktop.py`.

**Interfaces:** Consumes `Path.home()/Videos` and existing `QMediaPlayer`; produces an external-video record item whose data is `("external", Path)`.

- [ ] Add a Qt test with a temporary Videos folder showing that `show_records()` lists one MP4 and selecting it sets the player source to that path.
- [ ] Run `QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv/bin/pytest -q tests/test_desktop.py -k external_video`; confirm the feature assertion fails.
- [ ] Add only the `~/Videos/*.mp4` listing and direct detail playback, with a visible external-video analysis button.
- [ ] Rerun the focused test and full desktop test file; commit as `feat: play external Pi videos in records`.

### Task 2: Offline manual trigger to QR

**Files:** Modify `src/dashpi/desktop.py` and, only if necessary, add `src/dashpi/offline_video.py`; test `tests/test_desktop.py` and `tests/test_pipeline.py`.

**Interfaces:** Consume source `Path`, playback position seconds, `Settings`, `IncidentStore`, and `AnalysisWorker`; produce an `IncidentMetadata` through `IncidentPipeline.process(..., incident_offset_override=...)`.

- [ ] Write a failing short-MP4 test: an 11.87-second source triggered at 5 seconds preserves the source hash and yields an evidence clip with only available footage. Write a Qt test that a completed job opens the optical page and a failed job reports failure.
- [ ] Run focused tests; confirm intended failures.
- [ ] Probe source duration, clamp window bounds, construct `Segment(source, 0, duration)` and `IncidentMetadata.new(...)`, then submit the existing pipeline to `AnalysisWorker` without blocking Qt.
- [ ] Reuse `start_optical()` on `READY`; keep the existing incident detail and failure status for other outcomes. Rerun focused and full tests; commit as `feat: analyze imported video and display optical report`.

### Task 3: Full-screen and desktop launch

**Files:** Modify `src/dashpi/desktop.py`, `src/dashpi/desktop_install.py` if required; test `tests/test_desktop.py`, `tests/test_desktop_install.py`.

**Interfaces:** `dashpi-app` starts a full-screen `DashPiWindow`; `dashpi-install-desktop` creates a PCManFM-clickable icon.

- [ ] Add a failing Qt test that the main window starts full-screen; add a launcher regression test if launcher content changes.
- [ ] Run focused tests and confirm intended failures.
- [ ] Use `showFullScreen()` and fix the launcher-specific PCManFM prompt based on its actual MIME/click behavior, without changing global executable-file policy if avoidable.
- [ ] Rerun tests, `desktop-file-validate`, and a real Pi icon-click test; commit as `fix: launch DashPi full-screen without confirmation`.

### Task 4: Pi acceptance

**Files:** No new source files; update `README.md` only if user-facing operation differs.

- [ ] Run all local tests and `git diff --check`.
- [ ] Push the tested branch to the Pi's separate `~/DashPi-native` checkout without touching `~/DashPi/main`; reinstall the managed icon.
- [ ] Verify the transferred MP4 appears, opens, and can produce a report/QR or report the exact environment blocker; verify full-screen click behavior.
- [ ] Report measured results, remaining camera issue, and commits.
