"""Camera recording and device-local state for the native DashPi app."""

from __future__ import annotations

import csv
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from io import StringIO
import json
import math
from pathlib import Path
import shutil
import signal
import subprocess
import time
import uuid

from dashpi.models import Segment
from dashpi.media import probe_duration
from dashpi.storage import atomic_write


@dataclass(frozen=True)
class VideoSettings:
    width: int = 1920
    height: int = 1080
    fps: int = 30
    bitrate_mbps: int = 8
    brightness: float = 0.0
    ollama_model: str = "qwen2.5vl:3b"

    def __post_init__(self) -> None:
        if (self.width, self.height) not in {(1280, 720), (1920, 1080)}:
            raise ValueError("unsupported recording resolution")
        if type(self.fps) is not int or self.fps not in {24, 30}:
            raise ValueError("unsupported frame rate")
        if type(self.bitrate_mbps) is not int or self.bitrate_mbps not in {4, 8, 12}:
            raise ValueError("unsupported recording quality")
        if type(self.brightness) not in {int, float} or not math.isfinite(self.brightness) or not -1 <= self.brightness <= 1:
            raise ValueError("brightness must be between -1 and 1")
        if not isinstance(self.ollama_model, str) or not self.ollama_model.strip():
            raise ValueError("AI model is required")


def load_settings(path: Path) -> VideoSettings:
    if not path.exists():
        return VideoSettings()
    raw = json.loads(path.read_text())
    if type(raw) is not dict:
        raise ValueError("invalid device settings")
    return VideoSettings(**raw)


def save_settings(path: Path, settings: VideoSettings) -> None:
    atomic_write(path, json.dumps(asdict(settings), sort_keys=True).encode())


def pi_camera_command(settings: VideoSettings, segment_seconds: float, output: Path) -> list[str]:
    camera = shutil.which("rpicam-vid") or shutil.which("libcamera-vid")
    if camera is None:
        raise FileNotFoundError("rpicam-vid가 없습니다. Raspberry Pi 카메라 도구를 설치하세요.")
    return [
        camera, "--timeout", "0", "--codec", "h264", "--inline", "--profile", "baseline",
        "--intra", str(round(settings.fps * segment_seconds)),
        "--segment", str(round(segment_seconds * 1000)),
        "--width", str(settings.width), "--height", str(settings.height),
        "--framerate", str(settings.fps), "--bitrate", str(settings.bitrate_mbps * 1_000_000),
        "--brightness", str(settings.brightness), "-o", str(output),
    ]


@dataclass(frozen=True)
class Recording:
    session_id: str
    mode: str
    started_at: str
    segments: list[Segment]


class SegmentRecorder:
    def __init__(
        self,
        root: Path,
        settings: VideoSettings,
        *,
        camera_command: Callable[[Path], list[str]] | None = None,
        segment_seconds: float = 2.0,
    ) -> None:
        self.root, self.settings = root, settings
        self._camera_command = camera_command
        self.segment_seconds = segment_seconds
        self.recording = False
        self.mode: str | None = None
        self.session_dir: Path | None = None
        self.start_mono = 0.0
        self.camera: subprocess.Popen | None = None
        self.segments: list[Segment] = []
        self._camera_log = None

    def start(self, mode: str) -> None:
        if self.recording:
            raise RuntimeError("recording is already active")
        if mode not in {"drive", "parking"}:
            raise ValueError("invalid recording mode")
        if self.segment_seconds <= 0:
            raise ValueError("segment duration must be positive")
        if shutil.which("ffmpeg") is None:
            raise FileNotFoundError("FFmpeg가 없습니다.")
        self.session_dir = self.root / "raw" / uuid.uuid4().hex
        self.session_dir.mkdir(parents=True)
        pattern = self.session_dir / "%06d.h264"
        camera_command = (
            self._camera_command(pattern) if self._camera_command
            else pi_camera_command(self.settings, self.segment_seconds, pattern)
        )
        self.mode = mode
        self.segments = []
        self._camera_log = (self.session_dir / "camera.log").open("wb")
        try:
            self.camera = subprocess.Popen(
                camera_command, stdout=subprocess.DEVNULL, stderr=self._camera_log,
            )
            deadline = time.monotonic() + 10
            while not any(self.session_dir.glob("*.h264")):
                if self.camera.poll() is not None:
                    raise RuntimeError("카메라가 영상을 생성하지 못했습니다. camera.log를 확인하세요.")
                if time.monotonic() >= deadline:
                    raise TimeoutError("카메라 첫 영상 대기 시간이 초과되었습니다.")
                time.sleep(0.02)
            self.start_mono = time.monotonic()
            atomic_write(
                self.session_dir / "session.json",
                json.dumps({"mode": mode, "started_at": datetime.now(UTC).isoformat(),
                            "start_mono": self.start_mono}).encode(),
            )
            self.recording = True
        except BaseException:
            if self.camera is not None and self.camera.poll() is None:
                self.camera.terminate()
                self.camera.wait()
            self._close_logs()
            raise

    def poll(self) -> list[Segment]:
        if self.session_dir is None:
            return []
        self.segments = self._finalize_segments()
        if self.recording and self.camera.poll() not in (None, 0):
            raise RuntimeError("카메라 녹화가 중단되었습니다. camera.log를 확인하세요.")
        return self.segments

    def stop(self) -> None:
        if not self.recording:
            return
        try:
            if self.camera.poll() is None:
                self.camera.send_signal(signal.SIGINT)
            try:
                self.camera.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.camera.kill()
                self.camera.wait()
            self.segments = self._finalize_segments()
        finally:
            self.recording = False
            self._close_logs()

    def list_recordings(self) -> list[Recording]:
        recordings = []
        for metadata in (self.root / "raw").glob("*/session.json"):
            try:
                raw = json.loads(metadata.read_text())
                segments = self._segments_in(metadata.parent, float(raw["start_mono"]))
                if segments:
                    recordings.append(Recording(metadata.parent.name, raw["mode"], raw["started_at"], segments))
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return sorted(recordings, key=lambda item: item.started_at, reverse=True)

    def _finalize_segments(self) -> list[Segment]:
        segments = self._segments_in(self.session_dir, self.start_mono)
        listed = {segment.path for segment in segments}
        raw_paths = sorted(self.session_dir.glob("*.h264"))
        if self.camera is not None and self.camera.poll() is None:
            raw_paths = raw_paths[:-1]  # The camera still owns the newest file.
        for raw in raw_paths:
            output = raw.with_suffix(".mp4")
            if output in listed:
                continue
            if not output.exists():
                partial = output.with_name(output.name + ".partial")
                with (self.session_dir / "ffmpeg.log").open("ab") as log:
                    # ponytail: fixed-fps remux assumes the camera meets its target FPS; use --save-pts if Pi drift is measured.
                    subprocess.run(
                        ["ffmpeg", "-loglevel", "error", "-y", "-framerate", str(self.settings.fps),
                         "-f", "h264", "-i", str(raw), "-an", "-c:v", "copy",
                         "-f", "mp4", str(partial)],
                        check=True, stdout=subprocess.DEVNULL, stderr=log,
                    )
                partial.replace(output)
            start = segments[-1].end_mono if segments else self.start_mono
            segments.append(Segment(output, start, start + probe_duration(output)))
            buffer = StringIO()
            writer = csv.writer(buffer)
            for segment in segments:
                writer.writerow((segment.path.name, segment.start_mono - self.start_mono,
                                 segment.end_mono - self.start_mono))
            atomic_write(self.session_dir / "segments.csv", buffer.getvalue().encode())
        return segments

    @staticmethod
    def _segments_in(directory: Path, start_mono: float) -> list[Segment]:
        manifest = directory / "segments.csv"
        if not manifest.exists():
            return []
        segments = []
        with manifest.open(newline="") as source:
            for row in csv.reader(source):
                if len(row) != 3:
                    continue
                path = directory / Path(row[0]).name
                try:
                    start, end = float(row[1]), float(row[2])
                except ValueError:
                    continue
                if path.is_file() and 0 <= start < end:
                    segments.append(Segment(path, start_mono + start, start_mono + end))
        return segments

    def _close_logs(self) -> None:
        if self._camera_log is not None:
            self._camera_log.close()
        self._camera_log = None
