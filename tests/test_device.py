import pytest
import time


def synthetic_segmented_camera(duration, segment_seconds):
    def command(pattern):
        return [
            "ffmpeg", "-loglevel", "error", "-re", "-f", "lavfi", "-i",
            "testsrc=size=160x90:rate=30", "-t", str(duration), "-an", "-c:v", "libx264",
            "-g", "1", "-bf", "0", "-x264-params", "repeat-headers=1",
            "-f", "segment", "-segment_time", str(segment_seconds),
            "-segment_format", "h264", str(pattern),
        ]

    return command


def test_video_settings_persist_and_reject_invalid_update(tmp_path):
    from dashpi.device import VideoSettings, load_settings, save_settings

    path = tmp_path / "settings.json"
    chosen = VideoSettings(width=1280, height=720, fps=24, bitrate_mbps=8, brightness=0.2,
                           ollama_model="qwen2.5vl:3b")
    save_settings(path, chosen)

    assert load_settings(path) == chosen
    with pytest.raises(ValueError):
        save_settings(path, VideoSettings(width=111, height=720))
    assert load_settings(path) == chosen


def test_recorder_preserves_duration_of_camera_segments(tmp_path):
    from dashpi.device import SegmentRecorder, VideoSettings
    from dashpi.media import probe_duration

    recorder = SegmentRecorder(
        tmp_path, VideoSettings(), camera_command=synthetic_segmented_camera(4.2, 2),
        segment_seconds=2,
    )

    recorder.start("drive")
    recorder.camera.wait(timeout=15)
    recorder.stop()

    assert recorder.recording is False
    assert len(recorder.segments) >= 2
    assert all(segment.path.exists() and probe_duration(segment.path) > 0 for segment in recorder.segments)
    assert 4.1 <= sum(segment.end_mono - segment.start_mono for segment in recorder.segments) <= 4.3


def test_recorded_sessions_are_listed_by_mode(tmp_path):
    from dashpi.device import SegmentRecorder, VideoSettings

    recorder = SegmentRecorder(
        tmp_path, VideoSettings(), camera_command=synthetic_segmented_camera(2.5, 1),
        segment_seconds=1,
    )
    recorder.start("parking")
    recorder.camera.wait(timeout=15)
    recorder.stop()

    recordings = recorder.list_recordings()
    assert len(recordings) == 1
    assert recordings[0].mode == "parking"
    assert len(recordings[0].segments) >= 2
    assert recordings[0].segments[0].path.exists()


def test_pi_camera_uses_native_segment_rotation(monkeypatch, tmp_path):
    from dashpi.device import VideoSettings, pi_camera_command

    monkeypatch.setattr("dashpi.device.shutil.which", lambda name: "/usr/bin/rpicam-vid" if name == "rpicam-vid" else None)
    pattern = tmp_path / "%06d.h264"

    command = pi_camera_command(VideoSettings(), 2, pattern)

    assert command[command.index("--segment") + 1] == "2000"
    assert command[-2:] == ["-o", str(pattern)]
    assert "--inline" in command


def test_recording_time_starts_at_first_camera_segment(tmp_path):
    from dashpi.device import SegmentRecorder, VideoSettings

    def delayed_camera(pattern):
        return ["/bin/sh", "-c", 'sleep 0.5; exec "$@"', "sh",
                *synthetic_segmented_camera(0.4, 0.2)(pattern)]

    recorder = SegmentRecorder(
        tmp_path, VideoSettings(), camera_command=delayed_camera, segment_seconds=0.2,
    )
    before = time.monotonic()
    recorder.start("drive")
    recorder.camera.wait(timeout=10)
    recorder.stop()

    assert recorder.start_mono >= before + 0.4
