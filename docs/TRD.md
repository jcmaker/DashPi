# TRD — DashPi

## Runtime Architecture

DashPi runs one local Python application on a Raspberry Pi. The application owns recording, incident creation, Ollama analysis, result storage, the local API, and the DashPi display UI. It performs no cloud requests.

Two browser clients use the same visual language but have different runtime roles:

- **Local web UI:** served directly by DashPi after the phone joins its on-demand hotspot; used for report viewing and large downloads.
- **Optical receiver PWA:** installed from a trusted HTTPS origin before offline operation; used to receive animated QR streams without any network connection.

## Components

- `recorder.py` — creates short recording segments and enforces the raw-video ring limit
- `incidents.py` — handles physical/display triggers and incident state
- `clips.py` — selects and joins pre/post-trigger segments
- `reasoning.py` — samples frames and calls a local, vision-capable Ollama model
- `reports.py` — writes structured JSON and human-readable HTML reports
- `storage.py` — atomic writes, hashes, retention, and result lookup
- `api.py` — FastAPI status, result listing, viewing, and ranged downloads
- `optical.py` — DashPi optical container, fountain encoder, and QR frame generation
- `display/` — local controls, status, incident selection, hotspot control, and optical sender
- `web/` — local result viewer and installable optical receiver PWA

These are modules in one application, not independently deployed services.

## Incident State Flow

`recording → collecting_post_trigger → clipping → analyzing → ready`

Failure states preserve completed work:

- Clip failure: `clip_failed`
- AI failure after a valid clip: `analysis_failed`
- Transfer failure does not change incident state

## Recording and Clip Extraction

- Default segment duration: 2 seconds
- Default incident window: 30 seconds before and 15 seconds after the trigger
- Raw recording may use at most 70% of the DashPi data partition while retaining at least 10% free space.
- Oldest unprotected raw segments are removed first.
- Segments referenced by an active incident are protected until clip creation finishes.
- Completed incident clips are never deleted automatically in the MVP.
- Recording segment duration, pre/post window, and storage thresholds are installation settings.

Desktop development accepts a sample MP4 as the recording source. Raspberry Pi deployment replaces that source with Picamera2 without changing incident, clip, analysis, storage, or transfer behavior.

## Local AI Analysis

- A configured vision-capable Ollama model runs on the same device.
- The model name is an installation setting and is validated at startup.
- Analysis uses 12 evenly spaced JPEG frames from the incident clip to bound compute and memory use.
- The report records the model name, generation time, source clip digest, summary, timestamped observations, and limitations.
- Missing models, timeouts, and invalid model output produce `analysis_failed`; they never delete or invalidate the clip.
- Reports are advisory descriptions, not determinations of legal fault.

## Local Wi-Fi Transfer

- The Wi-Fi hotspot is off during normal driving.
- The user starts it from the DashPi display when a transfer is needed.
- The hotspot uses WPA2 and an installation-specific passphrase shown from the device settings.
- FastAPI binds only to the local hotspot interface in transfer mode.
- The local UI lists completed incidents and serves reports and clips.
- Video responses support standard HTTP Range requests for resume and seeking.
- The hotspot stops after 10 minutes without a connected client or an active transfer; the timeout is configurable.

## Optical Transfer

DashPi adopts the general ideas of animated QR transfer and LT fountain coding from Decimen Optical Transfer, but does not copy its current AGPL-3.0-or-later implementation or claim wire compatibility.

### DashPi Optical v1

- One-way display-to-camera transport with no handshake or back-channel
- Versioned, self-identifying binary frames
- Random session ID and monotonically increasing sequence number
- LT fountain symbols so the receiver may recover from dropped or reordered frames
- Per-frame consistency checks and final SHA-256 verification
- Container metadata for filename, media type, byte length, and optional compression when it reduces size
- 16 MiB MVP payload limit to keep mobile memory and transfer time bounded
- Configurable QR payload size, display scale, and frame rate for physical calibration

The first implementation is tested against fixed golden vectors. A protocol byte change requires a version change or a backward-compatible flag.

The optical channel is not confidential: any camera with a compatible decoder can capture it. The sender must display this warning before transmission. Encryption and pairing are outside the MVP.

## Mobile Web Behavior

- Full-size video transfer uses the local web UI served by DashPi; it does not depend on an installed application.
- Optical reception uses a PWA installed before offline operation because mobile default camera apps cannot reconstruct fountain-coded animated QR streams.
- The installed PWA caches its application assets but does not persist received content unless the user saves it.
- A received file is exposed only after its SHA-256 digest passes.
- Camera decoding must support current iOS and Android browsers through a portable QR decoder rather than relying only on `BarcodeDetector`.

## Local API

- `POST /api/incidents` — development/display trigger routed through the same handler as the hardware button
- `GET /api/status` — recorder, model, storage, and transfer status
- `GET /api/incidents` — completed and failed incident summaries
- `GET /api/incidents/{incident_id}` — incident metadata and report
- `GET /api/incidents/{incident_id}/clip` — ranged incident video response
- `GET /api/incidents/{incident_id}/report.html` — human-readable report

The API has no internet-facing deployment mode in the MVP.

## Storage Layout

Default data root: `/var/lib/dashpi`

- `/var/lib/dashpi/raw/` — loop-recording segments
- `/var/lib/dashpi/incidents/{incident_id}/clip.mp4`
- `/var/lib/dashpi/incidents/{incident_id}/report.json`
- `/var/lib/dashpi/incidents/{incident_id}/report.html`
- `/var/lib/dashpi/incidents/{incident_id}/metadata.json`

Files are written with a `.partial` suffix, flushed, and atomically renamed only after completion. Metadata marks a result complete only after required hashes are stored.

## Technology Choices

- Python 3
- FastAPI and Uvicorn
- OpenCV and FFmpeg
- Picamera2 on Raspberry Pi
- Ollama for local inference
- Browser standards for the local UI and PWA
- A portable browser QR decoder for iOS/Android compatibility

## Verification Without Hardware

- Use sample MP4 files as deterministic camera input.
- Verify pre/post clip boundaries within one 2-second segment.
- Replace the live model with deterministic report output only in integration tests.
- Exercise the real Ollama HTTP path when a local vision model is available.
- Round-trip optical containers through deterministic frame loss and reordering.
- Verify local API range download and SHA-256 integrity.
- Run the complete test suite with outbound network access unavailable.

## Hardware Acceptance Later

The Raspberry Pi, camera, and display are required only for final acceptance of:

- Picamera2 capture stability and timestamp accuracy
- Physical trigger wiring and debounce
- Display brightness, QR scale, frame rate, and camera decode rate
- Hotspot startup and mobile captive-portal behavior
- Ollama latency, memory, temperature, and power behavior
- Safe shutdown and recovery after sudden power loss
