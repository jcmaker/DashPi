import json
import math
import os
import subprocess
import tempfile
from pathlib import Path

from dashpi.models import FileArtifact, Segment
from dashpi.storage import sha256_file


def transfer_window(incident_offset: float, evidence_duration: float) -> tuple[float, float]:
    if not math.isfinite(incident_offset) or not 0.0 <= incident_offset <= evidence_duration:
        raise ValueError("incident timestamp outside evidence clip")
    duration = min(10.0, evidence_duration)
    start = min(max(0.0, incident_offset - 5.0), evidence_duration - duration)
    return start, start + duration


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def segment_source(source: Path, output_dir: Path, segment_seconds: float) -> list[Segment]:
    output_dir.mkdir(parents=True, exist_ok=True)
    pattern = output_dir / "%06d.mp4"
    list_fd, list_name = tempfile.mkstemp(dir=output_dir, suffix=".segments.txt")
    os.close(list_fd)
    segment_list = Path(list_name)
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source),
                "-map",
                "0:v:0",
                "-an",
                "-c:v",
                "libx264",
                "-force_key_frames",
                f"expr:gte(t,n_forced*{segment_seconds})",
                "-f",
                "segment",
                "-segment_time",
                str(segment_seconds),
                "-reset_timestamps",
                "1",
                "-segment_list",
                str(segment_list),
                str(pattern),
            ],
            check=True,
        )
        paths = [output_dir / path for path in segment_list.read_text().splitlines()]
    finally:
        segment_list.unlink(missing_ok=True)
    start, segments = 0.0, []
    for path in paths:
        end = start + probe_duration(path)
        segments.append(Segment(path, start, end))
        start = end
    return segments


def build_clip(
    segments: list[Segment], output: Path, window_start: float, duration: float
) -> FileArtifact:
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(output.name + ".partial")
    manifest = output.with_suffix(".concat.txt")
    manifest.write_text(
        "".join(
            f"file '{segment.path.as_posix().replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'\n"
            for segment in segments
        )
    )
    offset = max(0.0, window_start - segments[0].start_mono)
    try:
        command = [
            "ffmpeg",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(manifest),
        ]
        if offset:
            command.extend(["-ss", str(offset), "-t", str(duration), "-c:v", "libx264"])
        else:
            command.extend(["-t", str(duration), "-c", "copy"])
        command.extend(["-f", "mp4", str(partial)])
        subprocess.run(command, check=True)
        if offset and probe_duration(partial) < duration - 0.1:
            raise RuntimeError("clip did not preserve requested duration")
        with partial.open("rb") as completed:
            os.fsync(completed.fileno())
        digest, byte_length = sha256_file(partial), partial.stat().st_size
        partial.replace(output)
        return FileArtifact(output, byte_length, digest)
    finally:
        manifest.unlink(missing_ok=True)


def transcode_clip(
    source: Path,
    output: Path,
    start: float,
    duration: float,
    height: int,
    bitrate: str,
) -> FileArtifact:
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(output.name + ".partial")
    subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            str(start),
            "-i",
            str(source),
            "-t",
            str(duration),
            "-an",
            "-vf",
            f"scale=-2:{height}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-b:v",
            bitrate,
            "-movflags",
            "+faststart",
            "-f",
            "mp4",
            str(partial),
        ],
        check=True,
    )
    if probe_duration(partial) < duration - 0.1:
        raise RuntimeError("clip did not preserve requested duration")
    with partial.open("rb") as completed:
        os.fsync(completed.fileno())
    digest, byte_length = sha256_file(partial), partial.stat().st_size
    partial.replace(output)
    return FileArtifact(output, byte_length, digest)


def extract_frame(source: Path, output: Path, timestamp: float) -> FileArtifact:
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(output.name + ".partial")
    subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            str(timestamp),
            "-i",
            str(source),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            "-f",
            "image2",
            str(partial),
        ],
        check=True,
    )
    with partial.open("rb") as completed:
        os.fsync(completed.fileno())
    digest, byte_length = sha256_file(partial), partial.stat().st_size
    partial.replace(output)
    return FileArtifact(output, byte_length, digest)


def sample_frames(clip: Path, output_dir: Path, count: int) -> list[tuple[Path, float]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    duration = probe_duration(clip)
    paths = []
    for index in range(count):
        target = output_dir / f"{index:02d}.jpg"
        timestamp = duration * (index + 0.5) / count
        subprocess.run(
            [
                "ffmpeg",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                str(timestamp),
                "-i",
                str(clip),
                "-frames:v",
                "1",
                str(target),
            ],
            check=True,
        )
        paths.append((target, timestamp))
    return paths
