import sys
from types import ModuleType, SimpleNamespace

import pytest


@pytest.fixture
def fake_picamera2(monkeypatch):
    state = SimpleNamespace(created=0, started=0, closed=0)

    class Camera:
        def __init__(self):
            state.created += 1
            self.configuration = None
            self.output = None

        def create_video_configuration(self, **kwargs):
            return kwargs

        def configure(self, configuration):
            self.configuration = configuration

        def set_controls(self, controls):
            self.controls = controls

        def start_recording(self, encoder, output):
            state.started += 1
            self.output = output
            encoder.firsttimestamp = 100_000_000
            output.start()

        def stop_recording(self):
            self.output.stop()

        def close(self):
            state.closed += 1

    class Encoder:
        def __init__(self, **kwargs):
            self.options = kwargs
            self.firsttimestamp = None
            self.forced_keyframes = 0

        def force_key_frame(self):
            self.forced_keyframes += 1

    class Output:
        def __init__(self, path):
            self.path = path

        def start(self):
            self.path.write_bytes(b"mp4")

        def stop(self):
            pass

    class Splitter:
        def __init__(self, output):
            self.output = output

        def start(self):
            self.output.start()

        def split_output(self, new_output):
            self.output.stop()
            self.output = new_output
            self.output.start()

        def stop(self):
            self.output.stop()

    class Preview:
        def __init__(self, camera, parent=None):
            self.camera = camera

    package = ModuleType("picamera2")
    package.Picamera2 = Camera
    encoders = ModuleType("picamera2.encoders")
    encoders.LibavH264Encoder = Encoder
    outputs = ModuleType("picamera2.outputs")
    outputs.PyavOutput = Output
    outputs.SplittableOutput = Splitter
    previews = ModuleType("picamera2.previews")
    qt = ModuleType("picamera2.previews.qt")
    qt.QGlSide6Picamera2 = Preview
    for name, module in (
        ("picamera2", package),
        ("picamera2.encoders", encoders),
        ("picamera2.outputs", outputs),
        ("picamera2.previews", previews),
        ("picamera2.previews.qt", qt),
    ):
        monkeypatch.setitem(sys.modules, name, module)
    return state, outputs


def test_single_camera_previews_and_closes_timestamped_segments(fake_picamera2, monkeypatch, tmp_path):
    from dashpi.device import VideoSettings
    from dashpi.pi_camera import PiCameraRecorder

    state, _ = fake_picamera2
    monkeypatch.setattr("dashpi.pi_camera.probe_duration", lambda path: 2.0)
    recorder = PiCameraRecorder(tmp_path, VideoSettings())
    recorder.prepare()
    preview = recorder.create_preview()
    assert preview.camera is recorder.picam2
    recorder.start("drive")
    assert len(recorder.split()) == 1
    assert recorder._encoder.forced_keyframes == 0  # breaks on Pi's Picamera2 + PyAV 14; iperiod aligns GOPs
    result = recorder.stop()

    assert state.created == state.started == state.closed == 1
    assert [item.path.name for item in result] == ["000000.mp4", "000001.mp4"]
    assert [(item.start_mono, item.end_mono) for item in result] == [(100.0, 102.0), (102.0, 104.0)]
    assert all(item.path.is_file() for item in result)
    assert recorder.list_recordings()[0].mode == "drive"


def test_missing_split_api_fails_before_camera_start(fake_picamera2, tmp_path):
    from dashpi.device import VideoSettings
    from dashpi.pi_camera import PiCameraRecorder

    state, outputs = fake_picamera2
    del outputs.SplittableOutput
    recorder = PiCameraRecorder(tmp_path, VideoSettings())

    with pytest.raises(RuntimeError, match="Picamera2.*업데이트"):
        recorder.prepare()
    assert state.created == state.started == 0


def test_start_failure_preserves_original_error_and_closes_camera(fake_picamera2, monkeypatch, tmp_path):
    from dashpi.device import VideoSettings
    from dashpi.pi_camera import PiCameraRecorder

    state, _ = fake_picamera2
    camera_type = sys.modules["picamera2"].Picamera2

    def failed_start(self, encoder, output):
        raise RuntimeError("encoder failed")

    def failed_stop(self):
        raise RuntimeError("not started")

    monkeypatch.setattr(camera_type, "start_recording", failed_start)
    monkeypatch.setattr(camera_type, "stop_recording", failed_stop)
    recorder = PiCameraRecorder(tmp_path, VideoSettings())
    recorder.prepare()
    recorder.create_preview()

    with pytest.raises(RuntimeError, match="encoder failed"):
        recorder.start("drive")
    assert state.closed == 1
    assert recorder.picam2 is None


def test_camera_applies_brightness_setting(fake_picamera2, tmp_path):
    from dashpi.device import VideoSettings
    from dashpi.pi_camera import PiCameraRecorder

    recorder = PiCameraRecorder(tmp_path, VideoSettings(brightness=0.2))
    recorder.prepare()
    try:
        assert recorder.picam2.controls == {"Brightness": 0.2}
    finally:
        recorder.picam2.close()


def test_pruned_segments_never_reuse_an_mp4_name(fake_picamera2, monkeypatch, tmp_path):
    from dashpi.device import VideoSettings
    from dashpi.pi_camera import PiCameraRecorder

    monkeypatch.setattr("dashpi.pi_camera.probe_duration", lambda path: 2.0)
    recorder = PiCameraRecorder(tmp_path, VideoSettings())
    recorder.prepare()
    recorder.create_preview()
    recorder.start("drive")
    recorder.split()
    recorder.split()
    surviving = recorder.segments[1].path
    recorder.segments.pop(0)  # Storage retention removed the oldest closed segment.
    recorder.split()
    recorder.stop()

    assert surviving.is_file()
    assert [segment.path.name for segment in recorder.segments] == [
        "000001.mp4", "000002.mp4", "000003.mp4"
    ]


def test_pending_stop_tolerates_empty_just_opened_tail(fake_picamera2, monkeypatch, tmp_path):
    from dashpi.device import VideoSettings
    from dashpi.pi_camera import PiCameraRecorder

    def duration(path):
        if path.name == "000001.mp4":
            raise RuntimeError("no video frames")
        return 2.0

    monkeypatch.setattr("dashpi.pi_camera.probe_duration", duration)
    recorder = PiCameraRecorder(tmp_path, VideoSettings())
    recorder.prepare()
    recorder.create_preview()
    recorder.start("drive")
    recorder.split()

    result = recorder.stop(allow_empty_tail=True)

    assert [segment.path.name for segment in result] == ["000000.mp4"]
    assert (recorder.session_dir / "000001.mp4").exists()  # Preserve even an unreadable raw tail.


def test_pending_stop_does_not_hide_manifest_write_failure(fake_picamera2, monkeypatch, tmp_path):
    import dashpi.pi_camera as pi_camera
    from dashpi.device import VideoSettings
    from dashpi.pi_camera import PiCameraRecorder

    monkeypatch.setattr("dashpi.pi_camera.probe_duration", lambda path: 2.0)
    recorder = PiCameraRecorder(tmp_path, VideoSettings())
    recorder.prepare()
    recorder.create_preview()
    recorder.start("drive")
    recorder.split()
    original = pi_camera.atomic_write

    def fail_manifest(path, data):
        if path.name == "segments.csv":
            raise OSError("disk full")
        return original(path, data)

    monkeypatch.setattr("dashpi.pi_camera.atomic_write", fail_manifest)
    with pytest.raises(OSError, match="disk full"):
        recorder.stop(allow_empty_tail=True)


def test_split_times_out_instead_of_hanging_when_camera_frames_stop(fake_picamera2, monkeypatch, tmp_path):
    import threading
    from dashpi.device import VideoSettings
    from dashpi.pi_camera import PiCameraRecorder

    _, outputs = fake_picamera2
    never = threading.Event()
    monkeypatch.setattr(outputs.SplittableOutput, "split_output", lambda self, new_output: never.wait())
    recorder = PiCameraRecorder(tmp_path, VideoSettings())
    recorder.prepare()
    recorder.create_preview()
    recorder.start("drive")
    recorder.split_timeout = 0.2
    try:
        with pytest.raises(TimeoutError):
            recorder.split()
    finally:
        never.set()
