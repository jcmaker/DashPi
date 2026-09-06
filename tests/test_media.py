import pytest

from dashpi.media import (
    build_clip,
    extract_frame,
    probe_duration,
    sample_frames,
    segment_source,
    transcode_clip,
    transfer_window,
)
from dashpi.models import Segment
from tests.media_factory import make_video
from dashpi.storage import sha256_file


@pytest.mark.parametrize(
    ("incident", "expected"),
    [(22.5, (17.5, 27.5)), (2.0, (0.0, 10.0)), (44.0, (35.0, 45.0))],
)
def test_transfer_window_keeps_ten_seconds_at_boundaries(incident, expected):
    assert transfer_window(incident, 45.0) == expected


def test_transfer_window_uses_all_short_evidence():
    assert transfer_window(3.0, 8.0) == (0.0, 8.0)


def test_clip_and_twelve_samples(tmp_path):
    paths = [make_video(tmp_path / f"{n}.mp4", 2) for n in range(3)]
    segments = [Segment(path, n * 2.0, n * 2.0 + 2.0) for n, path in enumerate(paths)]

    artifact = build_clip(segments, tmp_path / "clip.mp4", window_start=0.0, duration=6.0)

    assert 5.8 <= probe_duration(artifact.path) <= 6.2
    assert len(sample_frames(artifact.path, tmp_path / "frames", 12)) == 12


def test_nonzero_clip_offset_preserves_requested_duration(tmp_path):
    paths = [make_video(tmp_path / f"{n}.mp4", 2) for n in range(3)]
    segments = [Segment(path, n * 2.0, n * 2.0 + 2.0) for n, path in enumerate(paths)]

    artifact = build_clip(segments, tmp_path / "clip.mp4", window_start=1.0, duration=3.0)

    assert 2.9 <= probe_duration(artifact.path) <= 3.1


def test_segment_source_ignores_stale_output_files(tmp_path):
    output_dir = tmp_path / "segments"
    output_dir.mkdir()
    stale = make_video(output_dir / "000001.mp4", 5)

    segments = segment_source(make_video(tmp_path / "source.mp4", 2), output_dir, 2.0)

    assert [segment.path.name for segment in segments] == ["000000.mp4"]
    assert stale.exists()


def test_transcode_builds_exact_ten_second_h264_derivative(tmp_path):
    source = make_video(tmp_path / "source.mp4", 12)

    artifact = transcode_clip(source, tmp_path / "annotated.mp4", 1.0, 10.0, 480, "900k")

    assert 9.9 <= probe_duration(artifact.path) <= 10.1
    assert artifact.sha256 == sha256_file(artifact.path)
    assert not (tmp_path / "annotated.mp4.partial").exists()


def test_extract_frame_is_atomic(tmp_path):
    source = make_video(tmp_path / "source.mp4", 2)

    frame = extract_frame(source, tmp_path / "moment.jpg", 1.0)

    assert frame.path.read_bytes().startswith(b"\xff\xd8")
    assert not (tmp_path / "moment.jpg.partial").exists()
