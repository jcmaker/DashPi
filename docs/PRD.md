# PRD — DashPi

## Product Overview

DashPi is an offline-first smart dashcam that preserves accident footage and generates a local AI report without an internet connection. Drivers review and export results through local web interfaces; no native mobile app or cloud account is required.

## Target User

- Individual drivers who need immediate access to accident evidence where internet service is unavailable or undesirable

## Core Value

> Understand and preserve an accident without depending on the cloud.

## Product Principles

- All recording, clip extraction, and AI analysis work without internet access.
- Driving does not require Wi-Fi or Bluetooth to remain enabled.
- Accident footage is preserved even when AI analysis or transfer fails.
- Large transfers use an on-demand local Wi-Fi link; small transfers may use an optical link.
- Hardware-dependent values remain configurable because camera, display, storage, and thermal behavior vary in the real device.

## MVP Features

- Continuous loop recording
- Accident trigger from a physical button or the DashPi display
- Configurable accident clip extraction, defaulting to 30 seconds before and 15 seconds after the trigger
- Local, vision-capable Ollama analysis
- Structured JSON report and human-readable HTML report
- On-demand local Wi-Fi hotspot for video and report download
- Fountain-coded animated QR transfer for reports and files up to 16 MiB
- Browser-based local viewing and an installable offline optical receiver PWA
- SHA-256 integrity verification for stored and transferred results

## User Flows

### Record and process an incident

1. DashPi records short video segments into a size-bounded ring buffer.
2. The driver presses the physical trigger or taps the DashPi display.
3. DashPi preserves the default 30-second pre-trigger and 15-second post-trigger window.
4. DashPi creates an incident clip and stores its SHA-256 digest.
5. Ollama analyzes sampled frames locally and produces JSON and HTML reports.
6. The DashPi display shows whether the clip and report are ready or whether analysis failed.

### Transfer over local Wi-Fi

1. The driver enables transfer mode from the DashPi display.
2. DashPi starts a WPA2 local hotspot and shows connection instructions.
3. The driver opens the DashPi local web page on the phone.
4. The driver previews reports or downloads the full video with resumable HTTP transfer.
5. DashPi turns off the hotspot after the configured idle timeout.

### Transfer optically

1. The driver selects a report or a file no larger than 16 MiB.
2. DashPi displays a fountain-coded animated QR stream and a confidentiality warning.
3. The phone's previously installed offline receiver PWA scans the display.
4. The PWA reconstructs frames in any order and verifies the file's SHA-256 digest.
5. The PWA offers the verified result for viewing or saving.

## Success Criteria

- A desktop simulation extracts a clip covering the configured pre/post window within one recording segment of tolerance.
- A sample incident completes the full offline flow: recording input, trigger, clip, local report, storage, and viewing.
- An AI failure leaves the incident clip intact and produces a visible `analysis_failed` status.
- A 100 MiB sample file downloads over the local API with HTTP Range resume and matches its SHA-256 digest.
- A 1 MiB optical test payload survives deterministic 15% frame loss and matches its SHA-256 digest.
- Runtime tests pass with outbound internet access disabled.
- Incomplete or corrupted results are never presented as complete.

## MVP Exclusions

- Cloud upload, cloud AI, remote accounts, and remote monitoring
- Native iOS or Android applications
- Mobile Bluetooth accident triggering
- Automatic crash detection
- Optical transfer as the default path for full-size video
- Confidential optical transfer
