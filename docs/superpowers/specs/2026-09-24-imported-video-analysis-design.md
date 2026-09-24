# Imported Video Analysis and Pi Launcher Design

**Date:** 2026-09-24
**Status:** Approved in conversation

## Experience

The Pi's `~/Videos/*.mp4` files appear in native **녹화기록** as external videos. Selecting one plays it in the existing Qt detail screen. A visible **사고 분석** button uses the current playback position as the manual trigger. The original file remains untouched and no microphone or GPS is used.

The supplied `CQkN1776752331_423_com.mp4` lasts 11.87 seconds. The app takes up to 30 seconds before and 15 seconds after the clicked position, limited to actual footage; it never invents missing frames. A missing, unreadable, or zero-duration file yields an inline error. AI or QR failure preserves the source and any completed evidence clip.

Analysis runs off the Qt thread through the existing `IncidentPipeline`, `IncidentStore`, local Ollama model, and report generator. The detail screen displays progress. On a ready report, the app opens its existing animated optical QR screen automatically; the existing report-QR control also remains available for later resend. An analysis failure is shown inline. The receiver remains the existing DashPi phone PWA.

The Pi app opens full-screen from the desktop icon. Clicking the icon must launch it directly, without PCManFM's executable-text confirmation. Do not globally disable script confirmation if a launcher-specific fix is possible.

## Implementation boundaries

The native UI scans the conventional Pi `~/Videos` directory; no new file-picker, database, copy/import pipeline, or dependency is needed. A single source video is passed as one `Segment` to the existing incident pipeline. The source window and incident offset are derived from the clicked position and probed duration; the generated evidence clip is stored in the normal incident store. This leaves live camera recording unchanged.

The desktop installer continues to own only its marked `DashPi.desktop` entries and icon. Launcher changes must preserve a valid desktop entry and must not overwrite unrelated user files. Pi-side validation checks the actual PCManFM click path, not just an executable bit or `desktop-file-validate` result.

## Verification

Use a failing Qt test for listing, playback-position triggering, progress, success-to-QR, and failure state; a short synthetic MP4 test verifies clipped bounds and the original SHA-256. Use a failing launcher test for any changed entry behavior. Run existing tests, then reinstall on Pi and check the transferred 11.87-second video, full-screen launch, no prompt, local Ollama report, and optical QR. Camera hardware remains a separate gate.
