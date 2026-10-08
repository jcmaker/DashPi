from datetime import UTC, datetime, timedelta
from dataclasses import replace
import json
import logging
from collections.abc import Callable
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

from dashpi import progress
from dashpi.ai_client import RetryableAnalysisError, retry_delay
from dashpi.config import OverlaySettings, Settings
from dashpi.media import (
    build_clip,
    extract_frame,
    probe_duration,
    sample_frames,
    transcode_clip,
    transfer_window,
)
from dashpi.models import IncidentMetadata, IncidentState, Segment
from dashpi.optical.container import MAX_PAYLOAD
from dashpi.reports import build_transfer_report, render_report_html, validate_report
from dashpi.ranges import _open_verified_file, _sha256_descriptor
from dashpi.storage import IncidentStore, atomic_write, sha256_file
from dashpi.vision import annotate_clip


class IncidentPipeline:
    def __init__(
        self,
        settings: Settings,
        store: IncidentStore,
        detector=None,
        wait_for_capacity: Callable[[], None] = lambda: None,
    ):
        self.settings = settings
        self.store = store
        self.detector = detector
        self.wait_for_capacity = wait_for_capacity

    def process(
        self,
        incident: IncidentMetadata,
        segments: list[Segment],
        analyze,
        incident_offset_override: float | None = None,
        overlays: OverlaySettings | None = None,
    ) -> IncidentMetadata:
        directory = self.store.directory(incident.incident_id)
        try:
            incident.transition(IncidentState.CLIPPING, datetime.now(UTC).isoformat())
            self.store.save(incident)
            progress.emit("clip", "start")
            window_start = incident.trigger_mono - self.settings.pre_seconds
            clip = build_clip(
                segments,
                directory / "clip.mp4",
                window_start,
                incident.post_deadline_mono - window_start,
            )
            incident.clip = replace(clip, duration=probe_duration(clip.path))
            progress.emit("clip", "done", f"{incident.clip.duration:.1f}초 · 지문 {clip.sha256[:8]}")
        except Exception as error:
            incident.transition(IncidentState.CLIP_FAILED, datetime.now(UTC).isoformat(), str(error))
            self.store.save(incident)
            return incident

        return self.generate_report(incident, analyze, incident_offset_override, overlays)

    def regenerate_report(
        self,
        incident_id: str,
        analyze,
        incident_offset_override: float | None = None,
        overlays: OverlaySettings | None = None,
    ) -> IncidentMetadata:
        self.wait_for_capacity()
        with self.store.open_incident(incident_id) as (incident, descriptor, directory):
            if (
                incident.incident_id != incident_id
                or incident.clip is None
                or incident.clip.duration is None
                or incident.clip.path != directory / "clip.mp4"
            ):
                raise ValueError("invalid evidence clip")
            source, _ = _open_verified_file(
                descriptor, "clip.mp4", incident.clip.byte_length, incident.clip.sha256
            )
            with source, TemporaryDirectory(prefix="dashpi-evidence-") as temporary:
                # Native media tools reopen paths. Give them only a private copy of
                # the verified descriptor, never the metadata-supplied pathname.
                evidence = Path(temporary) / "clip.mp4"
                source.seek(0)
                with evidence.open("wb") as output:
                    shutil.copyfileobj(source, output)
                return self.generate_report(
                    incident, analyze, incident_offset_override, overlays,
                    evidence_path=evidence, evidence_digest=lambda: _sha256_descriptor(source),
                )

    def generate_report(
        self,
        incident: IncidentMetadata,
        analyze,
        incident_offset_override: float | None = None,
        overlays: OverlaySettings | None = None,
        *,
        evidence_path: Path | None = None,
        evidence_digest: Callable[[], str] | None = None,
    ) -> IncidentMetadata:
        directory = self.store.directory(incident.incident_id)
        try:
            if incident.clip is None:
                raise ValueError("missing clip")
            evidence_path = evidence_path or incident.clip.path
            clip_before = sha256_file(evidence_path)
            if clip_before != incident.clip.sha256:
                raise ValueError("clip digest changed")
            incident.transition(IncidentState.ANALYZING, datetime.now(UTC).isoformat())
            self.store.save(incident)
            self.wait_for_capacity()
            progress.emit("frames", "start")
            frames = sample_frames(evidence_path, directory / "frames", self.settings.frame_sample_count)
            progress.emit("frames", "done", f"{len(frames)}장")
            generated_at = datetime.now(UTC).isoformat()
            self.wait_for_capacity()
            raw = analyze(frames, evidence_path, directory, incident_offset_override)
            analysis = raw.pop("analysis", None) if isinstance(raw, dict) else None
            report = validate_report(
                raw,
                incident.clip.sha256,
                self.settings.report_model_label,
                generated_at,
                incident.clip.duration,
                incident_offset_override,
            )
            if analysis is not None:
                report["analysis"] = analysis
            incident_offset = report["incident_timestamp"]
            progress.emit("build", "start")
            start, end = transfer_window(incident_offset, incident.clip.duration)
            active_overlays = overlays or self.settings.overlays
            keyframe_dir = directory / "keyframes"
            keyframe_timestamps = {}
            try:
                if self.detector is None:
                    raise RuntimeError("detector unavailable")
                self.wait_for_capacity()
                annotated, observations, keyframes = annotate_clip(
                    evidence_path,
                    directory / "annotated.mp4",
                    start,
                    end - start,
                    incident_offset,
                    self.detector,
                    active_overlays,
                    keyframe_dir,
                    480,
                    "900k",
                    keyframe_timestamps=keyframe_timestamps,
                )
                incident.annotated = annotated
                if probe_duration(annotated.path) < end - start - 0.1:
                    raise RuntimeError("annotated clip did not preserve requested duration")
                warnings = []
            except Exception:
                self.wait_for_capacity()
                annotated = transcode_clip(
                    evidence_path,
                    directory / "annotated.mp4",
                    start,
                    end - start,
                    480,
                    "900k",
                )
                incident.annotated = annotated
                last_frame = max(0.0, end - start - 0.1)
                moment = min(incident_offset - start, last_frame)
                selections = (max(0.0, moment - 2.0), moment, min(last_frame, moment + 2.0))
                keyframes = [
                    extract_frame(annotated.path, keyframe_dir / f"{role}.jpg", timestamp)
                    for role, timestamp in zip(("before", "moment", "after"), selections, strict=True)
                ]
                keyframe_timestamps = dict(zip(("before", "moment", "after"), (start + value for value in selections)))
                observations = []
                warnings = ["Object tracking failed; the transfer video has no boxes."]
            annotated = replace(annotated, duration=probe_duration(annotated.path))
            incident.annotated = annotated
            report.update(
                {
                    "incident_id": incident.incident_id,
                    "triggered_at": incident.triggered_at,
                    "transfer_window": {"start": start, "end": end},
                    "keyframe_timestamps": keyframe_timestamps,
                    "object_observations": observations,
                    "warnings": warnings,
                    "overlays": active_overlays.to_dict(),
                    "digests": {
                        "clip.mp4": incident.clip.sha256,
                        "annotated.mp4": annotated.sha256,
                        **{frame.path.name: frame.sha256 for frame in keyframes},
                    },
                }
            )
            report_html = render_report_html(
                report,
                annotated.path.read_bytes(),
                [frame.path.read_bytes() for frame in keyframes],
            ).encode()
            if len(report_html) > MAX_PAYLOAD:
                self.wait_for_capacity()
                annotated = transcode_clip(
                    annotated.path,
                    annotated.path,
                    0.0,
                    annotated.duration,
                    360,
                    "450k",
                )
                incident.annotated = annotated
                annotated = replace(annotated, duration=probe_duration(annotated.path))
                incident.annotated = annotated
                report["digests"]["annotated.mp4"] = annotated.sha256
                report_html = render_report_html(
                    report,
                    annotated.path.read_bytes(),
                    [frame.path.read_bytes() for frame in keyframes],
                ).encode()
                if len(report_html) > MAX_PAYLOAD:
                    report["warnings"].append("Optical payload exceeds 16 MiB; use Local Wi-Fi.")
                    report_html = render_report_html(
                        report,
                        annotated.path.read_bytes(),
                        [frame.path.read_bytes() for frame in keyframes],
                    ).encode()
            incident.report_json = atomic_write(
                directory / "report.json", json.dumps(report, sort_keys=True).encode()
            )
            incident.report_html = atomic_write(directory / "report.html", report_html)
            incident.report_transfer = None
            try:
                incident.report_transfer = atomic_write(
                    directory / "report.transfer.json",
                    build_transfer_report(report, [frame.path.read_bytes() for frame in keyframes], incident.clip.duration),
                )
            except Exception:
                logging.getLogger("dashpi").warning("Image report unavailable; HTML report preserved", exc_info=True)
            progress.emit("build", "done", f"{len(report_html) / 1_000_000:.1f} MB")
            if (
                sha256_file(evidence_path) != clip_before
                or clip_before != incident.clip.sha256
                or (evidence_digest is not None and evidence_digest() != clip_before)
            ):
                raise ValueError("clip digest changed")
            incident.annotated = annotated
            incident.incident_offset_seconds = incident_offset
            incident.report_model = self.settings.report_model_label
            incident.report_generated_at = generated_at
            incident.next_analysis_at = None
            incident.transition(IncidentState.READY, datetime.now(UTC).isoformat())
        except RetryableAnalysisError as error:
            now = datetime.now(UTC)
            incident.analysis_attempts += 1
            retry_at = error.retry_at or now + retry_delay(incident.analysis_attempts)
            incident.next_analysis_at = retry_at.isoformat()
            incident.transition(IncidentState.AWAITING_ANALYSIS, now.isoformat(), str(error))
        except Exception as error:
            incident.transition(IncidentState.ANALYSIS_FAILED, datetime.now(UTC).isoformat(), str(error))

        self.store.save(incident)
        return incident
