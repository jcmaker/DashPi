from dashpi.media import build_clip, probe_duration, sample_frames
from dashpi.models import Segment
from tests.media_factory import make_video


def test_clip_and_twelve_samples(tmp_path):
    paths = [make_video(tmp_path / f"{n}.mp4", 2) for n in range(3)]
    segments = [Segment(path, n * 2.0, n * 2.0 + 2.0) for n, path in enumerate(paths)]

    artifact = build_clip(segments, tmp_path / "clip.mp4", window_start=0.0, duration=6.0)

    assert 5.8 <= probe_duration(artifact.path) <= 6.2
    assert len(sample_frames(artifact.path, tmp_path / "frames", 12)) == 12
