# Native Raspberry Pi App Design

**Date:** 2026-09-24
**Status:** Approved for implementation; Pi 5 performance pending hardware verification

## User experience

Raspberry Pi 5 with 64-bit Raspberry Pi OS Desktop shows a DashPi launcher. Clicking it opens a standalone Python/PySide6 Qt Widgets window, with no browser, web view, QML, or Electron on the device. The supplied 16:9 wireframe guides the dark palette, large touch targets, and navigation. Home has **녹화기록**, **주행시작**, and **설정**. A top bar shows time and a recording indicator only when recording; it does not invent a battery reading.

**주행시작** opens a confirmation screen, then starts real camera recording. The recording screen has exactly two controls below the video: **사고 분석** and **종료**. **녹화기록** filters normal, event, and manually started parking recordings, and opens native video playback. An event detail shows the existing AI report from `report.json`; analysis failure still exposes the original clip. **설정** controls supported camera resolution, frame rate, quality, local AI model, and storage usage. Changes to capture settings apply on the next recording. Its **앱 종료** action asks for confirmation, defaults to cancellation, and uses the existing graceful window-close path only on confirmation.

**사고 분석** marks the press time as a manual incident trigger; it does not stop recording. DashPi retains the default 30 seconds before the press and continues capture for 15 seconds after it. Only after the post-trigger window is complete does it create the SHA-256-verifiable `clip.mp4` and start local video-only AI analysis. Without a pending incident, **종료** stops recording immediately. If **종료** is pressed during post-trigger collection, the screen shows that stopping is pending, completes the 15-second window, then stops automatically. Analysis and report generation may finish after recording stops. If the camera fails before the window completes, the app must report incomplete capture and preserve whatever raw video was recorded rather than claim a complete incident clip.

The **주행시작** confirmation offers drive and manually started parking recording; both use the same camera capture path. No ignition or battery sensing is implied. There are no microphone, voice, GPS, speed, or battery features. The AI uses camera frames only. Event creation follows the previously approved manual trigger followed by local AI analysis; continuous AI accident detection is a separate scope decision if requested.

The Raspberry Pi native app is required; a separate phone native app is not. The LCD is the default and fully sufficient control surface, including the manual incident trigger. After analysis, the Pi app displays animated optical QR frames for the existing offline receiver PWA on the phone. A normal QR camera cannot reconstruct this multi-frame transfer. Phone-side incident triggering is optional future work and requires a local return channel (for example, local Wi-Fi); optical QR transfer alone is one-way and cannot send a trigger back to the Pi.

Optical transfer uses the existing 16 MiB report limit. If the saved report exceeds it, the app states that QR transfer is unavailable and keeps the local report; this scope does not start a hotspot or silently switch to network transfer.

## Runtime

The native app calls the current Python incident pipeline and storage code directly. It does not require the local FastAPI server for its own display or a Rust frontend/process bridge. Camera capture, media work, and AI analysis must not block the Qt UI thread. The existing browser UI remains available for phone transfer only.

The recording screen must show the **live camera image inside the Qt window** while that same camera records; opening the camera from a second process is not an acceptable assumption. For the native app, Picamera2 owns the camera once, uses its PySide6 Qt preview widget, and encodes the same capture stream. Pi 5 has no H.264 hardware encoder, so the implementation uses Picamera2's `LibavH264Encoder`, with `SplittableOutput` and `PyavOutput` to close timestamped MP4 segments on keyframes without dropping frames. This replaces the `rpicam-vid` path for the native UI, not the existing synthetic tests or incident pipeline. The installed Raspberry Pi OS Picamera2 version must expose these APIs; if it does not, installation reports the missing capability rather than silently showing a stale or blank preview. The existing `rpicam-vid` segmented recorder remains as a tested fallback/prototype until Pi hardware verifies the new path.

A bounded raw recording history keeps recent normal and parking footage. Event segments remain protected while the 30-second pre-trigger and 15-second post-trigger clip is built. The current pipeline then writes the evidence clip and AI report in a worker so the UI stays responsive. Segment metadata uses the actual MP4 duration and a monotonic capture reference; camera/encoder startup delay, real Pi frame-rate drift, and trigger alignment need hardware acceptance.

The app runs after a desktop icon click; it does not start recording merely because the Pi boots. Startup and capture errors are shown plainly. Low storage must stop new capture without deleting saved incidents. A graceful close follows the same pending-stop rule as **종료**; forced power loss cannot guarantee a complete post-trigger window. The Ollama model may fail while capture continues; an event clip remains available as `analysis_failed`.

Picamera2 API references: [PySide6 preview example](https://github.com/raspberrypi/picamera2-examples/blob/main/examples/app_qtgl_pyside6.py), [seamless MP4 split example](https://github.com/raspberrypi/picamera2-examples/blob/main/examples/split_output.py), and [Picamera2 installation guidance](https://github.com/raspberrypi/picamera2#installation). These establish API intent, not a measured Pi 5 performance guarantee.

## Verification

Desktop tests use synthetic video and a fake camera backend to exercise recording, the two separate controls, delayed stopping, event timing, settings persistence, and Qt navigation. A packaged launcher smoke test checks the desktop entry. Raspberry Pi acceptance must confirm the Picamera2 API availability, simultaneous embedded preview and MP4 recording, timestamp alignment, screen scaling, storage pressure, heat, power loss recovery, and local Ollama latency on the actual device.

Before expanding the full UI, run a native shell on the Pi 5 and record cold launch time, idle memory, and button feedback while recording. During capture and AI work, a tap must produce visible feedback without waiting for those jobs to finish. Discover RAM on-device; if the vision model causes swapping or UI stalls, reduce its workload before replacing the Qt frontend. Qt dependency installation size is a storage cost, not proof of high idle memory. No performance claim is final until this gate is measured on the Pi.

Implementation proceeds in reviewable commits: (1) integrate the single-owner camera and validate preview/segment interfaces; (2) connect incident retention and delayed stopping; (3) add the native Qt screens and desktop launcher; (4) show optical QR frames from the saved report and document on-device acceptance. Each stage keeps the existing synthetic-media pipeline working and receives its own tests before commit.
