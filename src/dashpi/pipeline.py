from datetime import UTC, datetime
from dataclasses import replace
import json

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
from dashpi.reports import render_report_html, validate_report
from dashpi.storage import IncidentStore, atomic_write, sha256_file
from dashpi.vision import annotate_clip


class IncidentPipeline:
    def __init__(self, settings: Settings, store: IncidentStore, detector=None):
        self.settings = settings
        self.store = store
        self.detector = detector

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
            window_start = incident.trigger_mono - self.settings.pre_seconds
            clip = build_clip(
                segments,
                directory / "clip.mp4",
                window_start,
                incident.post_deadline_mono - window_start,
            )
            incident.clip = replace(clip, duration=probe_duration(clip.path))
        except Exception as error:
            incident.transition(IncidentState.CLIP_FAILED, datetime.now(UTC).isoformat(), str(error))
            self.store.save(incident)
            return incident

        return self.generate_report(incident, analyze, incident_offset_override, overlays)

    def generate_report(
        self,
        incident: IncidentMetadata,
        analyze,
        incident_offset_override: float | None = None,
        overlays: OverlaySettings | None = None,
    ) -> IncidentMetadata:
        directory = self.store.directory(incident.incident_id)
        try:
            if incident.clip is None:
                raise ValueError("missing clip")
            clip_before = sha256_file(incident.clip.path)
            if clip_before != incident.clip.sha256:
                raise ValueError("clip digest changed")
            incident.transition(IncidentState.ANALYZING, datetime.now(UTC).isoformat())
            self.store.save(incident)
            frames = sample_frames(incident.clip.path, directory / "frames", self.settings.frame_sample_count)
            generated_at = datetime.now(UTC).isoformat()
            report = validate_report(
                analyze(frames),
                incident.clip.sha256,
                self.settings.ollama_model,
                generated_at,
                incident.clip.duration,
                incident_offset_override,
            )
            incident_offset = report["incident_timestamp"]
            start, end = transfer_window(incident_offset, incident.clip.duration)
            active_overlays = overlays or self.settings.overlays
            keyframe_dir = directory / "keyframes"
            try:
                if self.detector is None:
                    raise RuntimeError("detector unavailable")
                annotated, observations, keyframes = annotate_clip(
                    incident.clip.path,
                    directory / "annotated.mp4",
                    start,
                    end - start,
                    incident_offset,
                    self.detector,
                    active_overlays,
                    keyframe_dir,
                    480,
                    "900k",
                )
                if probe_duration(annotated.path) < end - start - 0.1:
                    raise RuntimeError("annotated clip did not preserve requested duration")
                warnings = []
            except Exception:
                annotated = transcode_clip(
                    incident.clip.path,
                    directory / "annotated.mp4",
                    start,
                    end - start,
                    480,
                    "900k",
                )
                last_frame = max(0.0, end - start - 0.1)
                moment = min(incident_offset - start, last_frame)
                keyframes = [
                    extract_frame(annotated.path, keyframe_dir / "before.jpg", max(0.0, moment - 2.0)),
                    extract_frame(annotated.path, keyframe_dir / "moment.jpg", moment),
                    extract_frame(annotated.path, keyframe_dir / "after.jpg", min(last_frame, moment + 2.0)),
                ]
                observations = []
                warnings = ["Object tracking failed; the transfer video has no boxes."]
            annotated = replace(annotated, duration=probe_duration(annotated.path))
            report.update(
                {
                    "incident_id": incident.incident_id,
                    "triggered_at": incident.triggered_at,
                    "transfer_window": {"start": start, "end": end},
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
            incident.report_json = atomic_write(
                directory / "report.json", json.dumps(report, sort_keys=True).encode()
            )
            incident.report_html = atomic_write(
                directory / "report.html",
                render_report_html(
                    report,
                    annotated.path.read_bytes(),
                    [frame.path.read_bytes() for frame in keyframes],
                ).encode(),
            )
            if sha256_file(incident.clip.path) != clip_before or clip_before != incident.clip.sha256:
                raise ValueError("clip digest changed")
            incident.annotated = annotated
            incident.incident_offset_seconds = incident_offset
            incident.report_model = self.settings.ollama_model
            incident.report_generated_at = generated_at
            incident.transition(IncidentState.READY, datetime.now(UTC).isoformat())
        except Exception as error:
            incident.transition(IncidentState.ANALYSIS_FAILED, datetime.now(UTC).isoformat(), str(error))

        self.store.save(incident)
        return incident
