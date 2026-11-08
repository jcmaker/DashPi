# Saved video tracking implementation plan

**Goal:** Apply YOLO + ByteTrack to a saved video and produce a separate MP4 with boxes, IDs and recent movement trails, without an AI API call or changing the source.

**Architecture:** Reuse the existing OpenCV YOLO detector and `annotate_clip` renderer. Replace its frame-to-frame IoU matching with the already installed Supervision ByteTrack implementation. Use its trace annotator for recent paths. Add `dashpi track VIDEO --detector-model MODEL --output OUTPUT` and expose the result through the existing video browser by saving it under `~/Videos` on the Pi.

**Tech stack:** Python, OpenCV, Supervision 0.27, FFmpeg.

## Scope

- Modify `src/dashpi/vision.py`: ByteTrack and paths, safe whole-video export.
- Modify `src/dashpi/cli.py`: tracking command independent of GPT configuration.
- Modify `pyproject.toml`: declare the installed tracking dependency.
- Modify `tests/test_vision.py`, `tests/test_cli.py`: recovery across gaps and low confidence, visible trails, source/output preservation and offline command behavior.
- Modify `README.md`: usage and CPU/Hailo distinction.
- Keep the current recording UI work and device model settings.
- Preserve existing annotation validation, evidence hashes and fallback handling.

## Execution

- [x] Add tests proving IDs survive a short detection gap and a low-confidence detection; different objects get different IDs.
- [x] Add tests proving trajectories are drawn and tracking does not overwrite the source or an existing destination.
- [x] Run the tests against the old implementation and confirm failure.
- [x] Implement `ByteTracker.update(frame, detections, overlays)` using `sv.ByteTrack.update_with_detections` and `sv.TraceAnnotator`; return the existing detection dictionary shape with `track_id`.
- [x] Use ByteTracker in the existing annotation loop; remove the unused IoU assignment helpers and their obsolete test.
- [x] Implement `track_video(source, output, detector) -> FileArtifact`, rendering into a temporary directory beside the destination and publishing without replacing any existing file.
- [x] Add the CLI command, document the dependency and usage, then run vision, CLI, pipeline and desktop tests.
- [x] Apply the changed modules to the Pi after confirming they match the expected base.
- [x] Run real YOLO on an existing Pi video, verify the source digest, inspect a frame and provide the resulting MP4.

## Hardware boundary

The current Hailo-8 is not enumerated on PCIe. This step runs existing YOLO on the CPU and ByteTrack on the CPU; it does not claim Hailo acceleration. A correctly connected PCIe ribbon and working Hailo runtime/model are required for the later accelerator integration.

## Validation notes

Review fixes covered class isolation, confidence thresholds, incomplete export rejection, expired ID cleanup, and trails advancing across detection gaps. Relevant tracking/pipeline checks: 54 passed. Full Python suite: 557 passed, with 14 existing FastAPI deprecation warnings. Final independent vision/CLI review: 18 passed, no remaining significant findings. Actual local rendering using the Pi model preserved the source digest and produced the full 11.866667-second clip. Pi CPU inference completed in 122.9 seconds with OpenCV limited to one thread: 356 frames, full 11.866667-second duration, unchanged source SHA-256. Export: `/home/wonmaker/Videos/CQkN1776752331_423_com-tracked.mp4`. Local copy SHA-256 matches the Pi artifact; full FFmpeg decoding succeeded, and an eight-second frame shows vehicle/person boxes, IDs and paths. Hailo acceleration and live tracking remain outside this step.

## Final deployment scope

Per the user’s final instruction, keep this feature committed on local `dev` only. Do not merge to `main`, push or deploy to the Pi. Earlier temporary Pi changes to vision, CLI and project dependencies were restored to its HEAD, and the task-generated Pi demo was removed. Existing desktop UI and GPT settings were preserved. The last local-only label readability fix scales text before 480p export; it was not deployed to the Pi.
