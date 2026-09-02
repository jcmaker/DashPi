from datetime import UTC, datetime
import json

from dashpi.media import build_clip, sample_frames
from dashpi.models import IncidentMetadata, IncidentState, Segment
from dashpi.reports import render_report_html, validate_report
from dashpi.storage import IncidentStore, atomic_write


class IncidentPipeline:
    def __init__(self, settings, store: IncidentStore):
        self.settings = settings
        self.store = store

    def process(self, incident: IncidentMetadata, segments: list[Segment], analyze) -> IncidentMetadata:
        directory = self.store.directory(incident.incident_id)
        try:
            incident.transition(IncidentState.CLIPPING, datetime.now(UTC).isoformat())
            self.store.save(incident)
            window_start = incident.trigger_mono - self.settings.pre_seconds
            incident.clip = build_clip(
                segments,
                directory / "clip.mp4",
                window_start,
                incident.post_deadline_mono - window_start,
            )
        except Exception as error:
            incident.transition(IncidentState.CLIP_FAILED, datetime.now(UTC).isoformat(), str(error))
            self.store.save(incident)
            return incident

        try:
            incident.transition(IncidentState.ANALYZING, datetime.now(UTC).isoformat())
            self.store.save(incident)
            frames = sample_frames(incident.clip.path, directory / "frames", self.settings.frame_sample_count)
            report = validate_report(
                analyze(frames),
                incident.clip.sha256,
                self.settings.ollama_model,
                datetime.now(UTC).isoformat(),
            )
            incident.report_json = atomic_write(
                directory / "report.json", json.dumps(report, sort_keys=True).encode()
            )
            incident.report_html = atomic_write(
                directory / "report.html", render_report_html(report).encode()
            )
            incident.transition(IncidentState.READY, datetime.now(UTC).isoformat())
        except Exception as error:
            incident.transition(IncidentState.ANALYSIS_FAILED, datetime.now(UTC).isoformat(), str(error))

        self.store.save(incident)
        return incident
