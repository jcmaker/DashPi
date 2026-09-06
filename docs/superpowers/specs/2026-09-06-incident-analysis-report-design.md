# DashPi Incident Analysis Report Design

**Date:** 2026-09-06
**Status:** Approved for implementation planning
**Scope:** Manual incident triggering, precise incident localization, annotated transfer video, self-contained HTML reporting, and optical delivery

## 1. Decision Summary

DashPi remains a continuously recording, offline-first dashcam. The user manually marks a possible accident through the physical button, display, voice input, or a future app trigger. Every trigger enters the same incident handler.

The device preserves an immutable 45-second evidence clip covering 30 seconds before and 15 seconds after the trigger. Recording continues while analysis runs and always has priority over analysis work.

Local analysis finds the precise incident time inside the evidence clip. DashPi then creates a separate 10-second transfer video covering 5 seconds before and 5 seconds after that time. This derivative video contains object overlays and is embedded with the written analysis in one self-contained HTML report. The user starts optical transfer only after parking safely.

## 2. Alternatives Considered

### Self-contained HTML report — selected

One HTML file contains the report, annotated video, three printable stills, styles, and offline behavior. The existing single-file DashPi Optical v1 container can transfer it without a protocol change. The phone can immediately view or save the result.

### ZIP package

A ZIP would preserve separate MP4, JSON, and HTML files, but adds extraction and file-association steps on mobile. It is unnecessary for the MVP.

### Separate video and report transfers

This keeps each payload simple but requires two optical scans and makes it easier to separate the report from its source video. It is not selected.

## 3. User Flow

1. The user powers on DashPi and selects **Start recording** before driving.
2. DashPi records two-second video segments into the existing bounded ring.
3. After an accident, the user presses the physical button or invokes another manual trigger.
4. DashPi protects the segments covering the 30-second pre-trigger and 15-second post-trigger window.
5. Recording continues while the incident clip is built and analyzed.
6. Local analysis identifies the most likely incident timestamp in the 45-second clip.
7. DashPi extracts the 5 seconds before and 5 seconds after that timestamp.
8. Local detection and tracking produce the annotated transfer video and three key frames.
9. DashPi builds the self-contained HTML report and announces that the result is ready.
10. Optical transfer does not start automatically. After parking, the user selects **Send to phone**.
11. The phone receiver verifies the completed payload and opens the report.
12. The user may save the HTML or use **Save as PDF**.

## 4. Runtime Structure

DashPi remains one local Python application. No database, cloud service, native mobile application, or additional network service is introduced.

```text
ring recorder
  -> shared manual trigger handler
  -> immutable 45-second evidence clip
  -> precise incident localization
  -> 10-second derivative clip
  -> local detection and tracking
  -> annotated video and three key frames
  -> self-contained HTML report
  -> existing DashPi Optical v1 sender
```

Recording and incident processing are separate workloads in the same application. The recorder receives CPU, memory, storage I/O, and thermal priority. Analysis may slow down, pause, or resume rather than interrupt recording.

One detection pass over the 10-second derivative produces timestamped observations used by both the overlay renderer and the report. The implementation uses an installation-provided ONNX detector through OpenCV DNN and does not add a second inference service. Lane overlays use OpenCV image processing and are omitted if confidence is insufficient.

## 5. Trigger and Incident Timing

- Automatic crash detection is outside this scope because the device has no impact sensor.
- Physical button, display, voice, and future app actions route into the same manual trigger handler.
- The default evidence window is fixed at 30 seconds before and 15 seconds after the trigger.
- Overlapping triggers retain the existing behavior: extend the active incident instead of duplicating the same time range.
- The localized incident timestamp is stored as an offset from the evidence clip start.
- The transfer window is 5 seconds before and 5 seconds after the localized time, clamped to the available evidence boundaries.
- When boundary clamping shortens one side, DashPi extends the other side when possible so the derivative remains 10 seconds.

## 6. Evidence and Derived Artifacts

Each incident directory contains:

```text
clip.mp4       # immutable 45-second evidence clip without overlays
annotated.mp4  # 10-second transfer derivative with selected overlays
report.json    # structured analysis, timing, settings, warnings, and digests
report.html    # self-contained optical-transfer report
metadata.json  # incident state and artifact metadata
```

`clip.mp4` is never modified to add boxes, labels, or report data. Every completed artifact follows the existing partial-write, flush, SHA-256, atomic-rename, and metadata-update sequence.

`report.json` records:

- manual trigger time and localized incident offset
- evidence and transfer window boundaries
- object observations and confidence values
- overlay settings used to render `annotated.mp4`
- analysis summary, limitations, and warnings
- model identifiers and generation time
- SHA-256 digests for the evidence clip, annotated video, and report inputs

## 7. Object Overlays

Vehicles, motorcycles, bicycles, and pedestrians are tracked and shown by default. Objects most relevant to the incident are emphasized in red; other tracked road users use distinct, accessible colors and text labels.

The following display categories have independent on/off controls and default to off:

- traffic lights
- lane markings
- traffic signs

These controls affect only the derivative video's visual overlay. Detection and report analysis still use all available observations. Traffic lights and supported signs use labeled boxes; lane markings use line or region overlays. DashPi does not draw an object that the selected detector cannot identify with the configured confidence.

## 8. Self-contained HTML and PDF

The optical payload is one self-contained `report.html` file containing:

- the 10-second annotated H.264 MP4 as embedded data
- incident summary and detailed observations
- limitations and advisory-use warning
- the three annotated key frames: before, incident moment, and after
- artifact identifiers and SHA-256 values
- **Download HTML** and **Save as PDF** controls

The initial derivative is encoded at 480p with a bounded bitrate to fit the existing 16 MiB optical payload limit after HTML embedding. If the completed HTML exceeds the limit, DashPi lowers only the derivative resolution and bitrate and rebuilds it. It never alters the evidence clip. If the report still exceeds 16 MiB, optical transfer is unavailable and the UI directs the user to Local Wi-Fi transfer.

PDF export uses the browser's native print dialog. Print CSS hides the video player and interactive controls and includes the written report plus the three key frames. The PDF is therefore a static report; playable video remains in the saved HTML.

## 9. Transfer and Safety

- Analysis completion only displays a ready notification.
- Optical transfer starts only after an explicit **Send to phone** action.
- The device tells the user to park before starting the transfer.
- DashPi Optical v1 remains unchanged and carries `report.html` as one ordinary file.
- The receiver exposes the report only after container length and SHA-256 verification succeed.
- The optical channel remains unencrypted and displays the existing line-of-sight confidentiality warning.

## 10. Failure Handling

- Incident localization failure: preserve the evidence clip and allow the user to select the incident time manually before retrying report generation.
- Object tracking failure: generate an unannotated 10-second video and include a visible warning in the report.
- AI report failure: preserve all completed video artifacts and expose a retry action.
- Recorder contention: pause or slow analysis; never stop active recording to accelerate analysis.
- Optical payload over 16 MiB: rebuild the derivative at lower quality, then fall back to Local Wi-Fi if it still does not fit.
- Interrupted optical scan: keep the source report unchanged and allow a fresh scan.
- Digest mismatch: do not open, preview, or save the received result.
- PDF cancellation or failure: leave the HTML report available; PDF is a browser export, not an incident-state transition.

The existing incident states remain sufficient. Packaging work stays within `analyzing`; a valid fallback report may become `ready` with warnings. A failure that prevents a report becomes `analysis_failed` while the evidence clip remains available.

## 11. Verification

The smallest required automated checks cover:

- exact 10-second extraction around a centered incident time
- boundary clamping while retaining 10 seconds when the evidence clip permits
- continued recording while analysis is active
- unchanged evidence-clip digest before and after annotation
- default and custom overlay combinations
- unannotated fallback after tracker failure
- HTML containing embedded video, analysis, key frames, and offline controls
- print styling that contains three key frames and omits interactive video controls
- optical-size quality fallback and Local Wi-Fi fallback
- existing 15% frame-loss, duplicate-frame, reordered-frame, and SHA-256 optical checks

Raspberry Pi acceptance measures recording continuity, inference latency, CPU and memory pressure, thermal behavior, annotated-video encoding time, physical display readability, and phone-camera optical throughput.

## 12. Scope Boundary

This design does not add automatic collision sensing, legal fault determination, a native phone app, cloud processing, optical encryption, or PDF generation on the Raspberry Pi. Audio is not added to the current video-only MVP.

## 13. Reference and License Boundary

The optical concept was informed by [Decimen Optical Transfer](https://github.com/bashalarmistalt/decimen-optical-transfer): animated screen-to-camera QR transfer, LT fountain symbols, tolerance of dropped and reordered frames, session identity, and final SHA-256 verification.

DashPi does not copy Decimen source, wire bytes, golden vectors, decoder artifacts, or build outputs and does not claim compatibility. DashPi Optical v1 remains an independently specified `DPQ1`/`DPC1` protocol. Decimen is currently AGPL-3.0-or-later; incorporating any Decimen code requires a separate license decision.
