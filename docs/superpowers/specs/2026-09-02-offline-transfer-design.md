# DashPi Offline Incident and Transfer Design

**Date:** 2026-09-02
**Status:** Pending written review
**Scope:** Desktop-simulated incident pipeline, on-demand local transfer, and optical transfer proof of concept

## 1. Decision Summary

DashPi operates without internet access and without a native mobile application. A physical button or the DashPi display creates an incident. A local Python application preserves the accident clip, asks a local Ollama model for an advisory report, and exposes completed results through two user-selected transfer paths:

1. On-demand local Wi-Fi for full video and reports
2. Fountain-coded animated QR for reports and files up to 16 MiB

The local Wi-Fi path is the normal large-file path. The optical path is a network-free alternative for small payloads. Bluetooth triggering, cloud services, native mobile apps, automatic crash detection, and confidential optical transfer are outside this design.

## 2. Alternatives Considered

### Hybrid transfer — selected

Local Wi-Fi provides practical video throughput while optical transfer preserves a fully network-free option. The hotspot remains off while driving and exists only during user-initiated transfer.

### Optical-first transfer

This removes the Wi-Fi interaction but makes normal dashcam videos slow to export and occupies the DashPi display throughout transfer. It remains available as an explicit small-file option rather than the default.

### Local Wi-Fi only

This is simpler, but it does not meet the goal of adopting a display-to-camera path for environments where the user does not want to enable any network link.

## 3. System Boundary

### Inside DashPi

- Camera or deterministic sample-video source
- Ring recorder
- Incident trigger handler
- Clip extraction
- Local Ollama analysis
- Atomic local storage
- FastAPI local interface
- DashPi display controls
- Optical sender
- On-demand hotspot control

### On the phone

- Browser page served by DashPi for local Wi-Fi viewing and download
- Previously installed offline PWA for optical reception

### Outside the MVP

- Internet and cloud services
- Remote access
- Native phone applications
- Phone-based Bluetooth trigger
- Automatic impact sensing
- Legal fault determination

## 4. Incident Pipeline

The recorder writes 2-second segments into a bounded ring. A physical or display event enters the single incident trigger handler with a monotonic trigger timestamp. The handler protects all segments overlapping the 30 seconds before the trigger and schedules collection through 15 seconds after it.

After the post-trigger window closes, the clip component joins protected segments and trims the result to the requested window where the codec permits. The clip is written as `clip.mp4.partial`, flushed, hashed, and renamed to `clip.mp4`. Only then may the incident advance to analysis.

The reasoning component extracts 12 evenly spaced frames, submits them to the configured local Ollama vision model, validates the returned structure, and writes both JSON and HTML reports. The generated report identifies its source clip digest and model. A failed or unavailable model changes the incident to `analysis_failed` while leaving the valid clip downloadable.

## 5. Incident Data Model

Each incident has a generated identifier and one metadata document containing:

- `incident_id`
- wall-clock and monotonic trigger timestamps
- configured pre/post durations
- state and failure reason
- clip filename, byte length, duration, and SHA-256 digest
- report filename, model name, generation timestamp, and SHA-256 digest
- timestamps for each state transition

The report JSON contains:

- `summary`
- `observations`: timestamped visible events
- `limitations`: uncertainty, missing views, or model constraints
- `source_clip_sha256`
- `model`
- `generated_at`

Incident metadata is the source of truth for UI status. Directory presence alone never means a result is complete.

## 6. Storage and Recovery

The default root is `/var/lib/dashpi`. Raw recordings are expendable; incident clips are protected evidence.

- Raw data is limited to 70% of the data partition while at least 10% remains free.
- The oldest unprotected raw segments are deleted first.
- Active-incident segments stay protected until the clip is complete or the incident fails.
- Completed incident clips are not automatically deleted in the MVP.
- Every material output follows partial-write, flush, hash, atomic-rename, metadata-update order.
- On startup, stale partial files are reported and removed only when they are not referenced by an active incident.

## 7. Local Wi-Fi Transfer

The hotspot is disabled during normal recording. A user action on the DashPi display starts a WPA2 access point and the local FastAPI/UI process binds to that interface. The display shows the network and local page address.

The local page lists incidents, renders HTML reports, and streams clips with HTTP Range support. A transfer or connected client prevents idle shutdown. With neither present, the hotspot stops after 10 minutes by default.

The WPA2 passphrase is installation-specific and rotatable. The local API is not bound to an internet-facing interface and has no cloud deployment configuration in the MVP.

## 8. Optical Transfer

### Adopted concepts

DashPi adopts these general ideas from Decimen Optical Transfer:

- animated QR as a one-way display-to-camera channel
- LT fountain symbols rather than sequential chunks
- tolerance of dropped, duplicated, and reordered frames
- self-identifying versioned frames
- session identity without pairing
- final SHA-256 integrity verification

### License boundary

The current Decimen implementation is AGPL-3.0-or-later. DashPi will not copy its source, vendored decoder, byte layout, golden vectors, or build artifacts and will not claim Decimen compatibility. DashPi Optical v1 is an independently specified protocol using public algorithmic concepts. Any later decision to incorporate Decimen code requires a separate license decision before implementation.

### DashPi Optical v1 behavior

The sender packages one file with its name, media type, original length, optional compression marker, and SHA-256 digest. It splits the container into equal source blocks and continuously emits LT fountain symbols. Each QR frame identifies the DashPi protocol version, transfer session, sequence, block geometry, total payload length, and symbol integrity data.

The PWA accepts frames in any order, ignores duplicates, resets when a new session appears, and exposes the result only after container parsing and SHA-256 verification. Unknown protocol versions produce an explicit update message; unrelated QR codes remain silent.

MVP payloads are capped at 16 MiB. QR bytes per frame, display scale, and frames per second remain runtime calibration controls because the real display, phone camera, focus, and refresh rate determine reliable throughput.

The optical stream is not encrypted. The display warns that anyone with line of sight and a compatible receiver can capture it.

## 9. Web Delivery

The local web UI and optical PWA share presentation code but are delivered in different contexts:

- DashPi serves the local UI after the phone joins the hotspot. It performs same-origin local API calls and does not need installation.
- The optical receiver is installed from a trusted HTTPS origin before offline use. Its application assets are cached for offline startup, and its camera decoder requires no DashPi network connection.

Received optical bytes stay in memory until verification. The PWA persists content only after an explicit save action. The implementation uses a portable QR decoder because iOS Safari does not provide `BarcodeDetector`.

## 10. Error Handling

- Trigger while another incident is collecting: create a separate incident only when its requested time window does not overlap; otherwise extend the existing post-trigger deadline.
- Clip construction failure: mark `clip_failed`, retain protected source segments, and show a retry action.
- Ollama unavailable, timeout, or invalid output: mark `analysis_failed` and keep the clip available.
- Storage below the safety threshold: delete eligible raw segments; if none remain, stop new recording and show a blocking storage error without deleting incidents.
- Wi-Fi transfer interruption: retain the file and allow HTTP Range resume.
- Optical frame loss: continue emitting symbols until the user stops or the receiver finishes; corruption fails final verification.
- Unsupported optical protocol: show which receiver side requires an update.

## 11. Security and Privacy

- Runtime processing remains local and makes no outbound internet request.
- Local Wi-Fi uses WPA2 and binds services only to the local transfer interface.
- Reports clearly state that AI output is advisory and may be incomplete.
- Optical transfer displays a non-confidential-channel warning before transmission.
- The PWA does not automatically persist received evidence.
- File paths are generated from incident IDs; uploaded or transmitted filenames are never used as server paths.

## 12. Verification Strategy

Desktop verification uses a sample MP4 and deterministic timestamps. The smallest runnable checks cover:

- ring selection and the 30-second/15-second clip window
- overlapping-trigger deadline extension
- atomic output and recovery from stale partial files
- clip preservation across Ollama failure
- report schema and source digest
- API listing, report rendering, HTTP Range resume, and final hash
- fixed DashPi Optical v1 golden vectors
- optical round trip with duplicate, reordered, and 15% dropped frames
- rejection of malformed, oversized, unsupported, and hash-mismatched optical payloads
- full end-to-end operation with outbound internet unavailable

Real hardware acceptance later measures Picamera2 timing, physical button debounce, display/camera QR calibration, hotspot behavior, Ollama resource use, thermal limits, and sudden-power-loss recovery.

## 13. Implementation Order

1. Deterministic storage and incident state model
2. Sample-video ring recording and clip extraction
3. Local report generation and Ollama failure handling
4. FastAPI local result viewing and ranged download
5. DashPi Optical v1 container, fountain round trip, and golden vectors
6. Display sender and offline receiver PWA
7. Raspberry Pi camera, button, display, hotspot, and performance integration when hardware is available
