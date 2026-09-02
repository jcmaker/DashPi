import json
import os
import subprocess
from pathlib import Path

from dashpi.models import FileArtifact, Segment
from dashpi.storage import sha256_file


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
            str(pattern),
        ],
        check=True,
    )
    start, segments = 0.0, []
    for path in sorted(output_dir.glob("*.mp4")):
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
            command.extend(["-ss", str(offset)])
        command.extend(["-t", str(duration), "-c", "copy", "-f", "mp4", str(partial)])
        subprocess.run(command, check=True)
        with partial.open("rb") as completed:
            os.fsync(completed.fileno())
        digest, byte_length = sha256_file(partial), partial.stat().st_size
        partial.replace(output)
        return FileArtifact(output, byte_length, digest)
    finally:
        manifest.unlink(missing_ok=True)


def sample_frames(clip: Path, output_dir: Path, count: int) -> list[Path]:
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
        paths.append(target)
    return paths
