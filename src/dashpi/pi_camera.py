"""Single-owner Picamera2 capture for the native Raspberry Pi window."""

from __future__ import annotations

import csv
from contextlib import suppress
from datetime import UTC, datetime
from io import StringIO
import json
from pathlib import Path
import time
import uuid

from dashpi.device import Recording, SegmentRecorder, VideoSettings
from dashpi.media import probe_duration
from dashpi.models import Segment
from dashpi.storage import atomic_write


class PiCameraRecorder:
    def __init__(self, root: Path, settings: VideoSettings, segment_seconds: float = 2.0):
        self.root, self.settings, self.segment_seconds = root, settings, segment_seconds
        self.picam2 = None
        self._preview_type = None
        self._encoder_type = None
        self._splitter_type = None
        self._output_type = None
        self._preview = None
        self._splitter = None
        self._encoder = None
        self.session_dir: Path | None = None
        self.mode: str | None = None
        self.start_mono = 0.0
        self.segments: list[Segment] = []
        self.recording = False

    def prepare(self) -> None:
        if self.picam2 is not None:
            raise RuntimeError("camera is already prepared")
        try:
            from picamera2 import Picamera2
            from picamera2.encoders import LibavH264Encoder
            from picamera2.outputs import PyavOutput, SplittableOutput
            from picamera2.previews.qt import QGlSide6Picamera2
        except ImportError as error:
            raise RuntimeError(
                "필요한 Picamera2 API가 없습니다. Raspberry Pi OS와 python3-picamera2를 업데이트하세요."
            ) from error
        self._preview_type = QGlSide6Picamera2
        self._encoder_type = LibavH264Encoder
        self._splitter_type = SplittableOutput
        self._output_type = PyavOutput
        camera = Picamera2()
        try:
            configuration = camera.create_video_configuration(
                main={"size": (self.settings.width, self.settings.height)},
                controls={"FrameRate": self.settings.fps},
            )
            camera.configure(configuration)
            camera.set_controls({"Brightness": self.settings.brightness})
        except BaseException:
            camera.close()
            raise
        self.picam2 = camera

    def create_preview(self, parent=None):
        if self.picam2 is None or self._preview is not None:
            raise RuntimeError("prepare one camera before attaching its preview")
        self._preview = self._preview_type(self.picam2, parent=parent)
        return self._preview

    def start(self, mode: str) -> None:
        if mode not in {"drive", "parking"}:
            raise ValueError("invalid recording mode")
        if self.segment_seconds <= 0:
            raise ValueError("segment duration must be positive")
        if self.picam2 is None or self._preview is None or self.recording:
            raise RuntimeError("attach the camera preview before starting recording")
        self.session_dir = self.root / "raw" / uuid.uuid4().hex
        self.session_dir.mkdir(parents=True)
        self._encoder = self._encoder_type(
            bitrate=self.settings.bitrate_mbps * 1_000_000,
            iperiod=max(1, round(self.settings.fps * self.segment_seconds)),
            framerate=self.settings.fps,
        )
        self._splitter = self._splitter_type(self._output_type(self.session_dir / "000000.mp4"))
        started = False
        try:
            self.picam2.start_recording(self._encoder, self._splitter)
            started = True
            deadline = time.monotonic() + 10
            while self._encoder.firsttimestamp is None:
                if time.monotonic() >= deadline:
                    raise TimeoutError("카메라 첫 프레임 대기 시간이 초과되었습니다.")
                time.sleep(0.02)
            # SensorTimestamp is the capture clock; Pi hardware must validate its
            # alignment with Python's monotonic clock before release.
            self.start_mono = self._encoder.firsttimestamp / 1_000_000
            self.mode = mode
            self.segments = []
            atomic_write(
                self.session_dir / "session.json",
                json.dumps({"mode": mode, "started_at": datetime.now(UTC).isoformat(),
                            "start_mono": self.start_mono}).encode(),
            )
            self.recording = True
        except BaseException:
            if started:
                with suppress(Exception):
                    self.picam2.stop_recording()
            with suppress(Exception):
                self.picam2.close()
            self.picam2 = None
            raise

    def split(self) -> list[Segment]:
        if not self.recording:
            raise RuntimeError("recording is not active")
        closed = self.session_dir / f"{len(self.segments):06d}.mp4"
        next_path = self.session_dir / f"{len(self.segments) + 1:06d}.mp4"
        self._splitter.split_output(self._output_type(next_path))
        self._append_segment(closed)
        return list(self.segments)

    def stop(self) -> list[Segment]:
        if not self.recording:
            return list(self.segments)
        self.recording = False
        try:
            self.picam2.stop_recording()
            self._append_segment(self.session_dir / f"{len(self.segments):06d}.mp4")
        finally:
            self.picam2.close()
            self.picam2 = None
            self._preview = None
        return list(self.segments)

    def list_recordings(self) -> list[Recording]:
        recordings = []
        for metadata in (self.root / "raw").glob("*/session.json"):
            try:
                raw = json.loads(metadata.read_text())
                segments = SegmentRecorder._segments_in(metadata.parent, float(raw["start_mono"]))
                if segments:
                    recordings.append(Recording(metadata.parent.name, raw["mode"], raw["started_at"], segments))
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return sorted(recordings, key=lambda item: item.started_at, reverse=True)

    def _append_segment(self, path: Path) -> None:
        start = self.segments[-1].end_mono if self.segments else self.start_mono
        duration = probe_duration(path)
        if duration <= 0:
            raise RuntimeError("빈 카메라 영상 조각입니다.")
        self.segments.append(Segment(path, start, start + duration))
        buffer = StringIO()
        writer = csv.writer(buffer)
        for segment in self.segments:
            writer.writerow((segment.path.name, segment.start_mono - self.start_mono,
                             segment.end_mono - self.start_mono))
        atomic_write(self.session_dir / "segments.csv", buffer.getvalue().encode())
