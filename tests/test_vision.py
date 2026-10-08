import subprocess

import cv2
import numpy as np
import pytest

from dashpi.config import OverlaySettings
from dashpi.vision import YoloDetector, annotate_clip, draw_overlays

from tests.media_factory import make_video


DETECTIONS = [
    {"track_id": 1, "label": "car", "confidence": 0.91, "box": [20, 20, 80, 80]},
    {"track_id": 2, "label": "traffic light", "confidence": 0.88, "box": [90, 10, 115, 55]},
    {"track_id": 3, "label": "stop sign", "confidence": 0.82, "box": [5, 5, 18, 18]},
]


def changed_pixels(overlays, monkeypatch):
    frame = np.zeros((120, 120, 3), dtype=np.uint8)
    monkeypatch.setattr("dashpi.vision.lane_lines", lambda _frame: [(10, 110, 50, 60)])
    return np.count_nonzero(draw_overlays(frame.copy(), DETECTIONS, overlays))


def test_road_users_are_drawn_when_every_optional_layer_is_off(monkeypatch):
    assert changed_pixels(OverlaySettings(), monkeypatch) > 0


def test_optional_layers_change_output_independently(monkeypatch):
    baseline = changed_pixels(OverlaySettings(), monkeypatch)
    assert changed_pixels(OverlaySettings(traffic_lights=True), monkeypatch) > baseline
    assert changed_pixels(OverlaySettings(lanes=True), monkeypatch) > baseline
    assert changed_pixels(OverlaySettings(traffic_signs=True), monkeypatch) > baseline


def test_annotation_uses_detector_for_all_categories_but_hides_optional_boxes(tmp_path):
    source = make_video(tmp_path / "source.mp4", 2)
    calls = []

    def detector(frame):
        calls.append(frame.shape)
        return [
            {"label": "car", "confidence": 0.9, "box": [10, 10, 60, 60]},
            {"label": "traffic light", "confidence": 0.8, "box": [70, 5, 90, 40]},
        ]

    times = {}
    artifact, observations, keyframes = annotate_clip(
        source,
        tmp_path / "annotated.mp4",
        0.0,
        2.0,
        1.0,
        detector,
        OverlaySettings(),
        tmp_path / "keyframes",
        480,
        "900k",
        keyframe_timestamps=times,
    )
    assert calls
    assert {item["label"] for item in observations} == {"car", "traffic light"}
    assert len(keyframes) == 3
    assert artifact.path.exists()
    assert times == pytest.approx({"before": 0.0, "moment": 1.0, "after": 1.9})


def test_bytetrack_recovers_id_after_low_confidence_and_missing_detection():
    from dashpi.vision import ByteTracker

    tracker = ByteTracker(10)
    frame = np.zeros((120, 120, 3), dtype=np.uint8)
    def update(x, confidence=0.9):
        return tracker.update(frame, [{"label": "car", "confidence": confidence,
                                       "box": [x, 20, x + 40, 60]}], OverlaySettings())

    first = update(10)[0]["track_id"]
    assert update(12, 0.2)[0]["track_id"] == first
    assert tracker.update(frame, [], OverlaySettings()) == []
    assert update(16)[0]["track_id"] == first


def test_bytetrack_draws_paths_and_keeps_simultaneous_objects_distinct():
    from dashpi.vision import ByteTracker

    tracker = ByteTracker(10)
    for x in (10, 14, 18):
        frame = np.zeros((120, 120, 3), dtype=np.uint8)
        tracked = tracker.update(frame, [
            {"label": "car", "confidence": 0.9, "box": [x, 10, x + 30, 40]},
            {"label": "person", "confidence": 0.9, "box": [80, 10, 100, 40]},
            {"label": "traffic light", "confidence": 0.9, "box": [10, 70, 30, 100]},
        ], OverlaySettings())
    assert len({item["track_id"] for item in tracked}) == 3
    assert np.any(frame[38:43, 25:34])
    assert not np.any(frame[90:110])  # hidden traffic-light layer must not leave a path


def test_bytetrack_keeps_class_ids_separate_at_the_same_position():
    from dashpi.vision import ByteTracker

    tracker = ByteTracker(10)
    frame = np.zeros((120, 120, 3), dtype=np.uint8)
    def update(label):
        return tracker.update(frame, [{"label": label, "confidence": 0.9,
                                       "box": [20, 20, 60, 60]}], OverlaySettings())

    car_id = update("car")[0]["track_id"]
    person = update("person") or update("person")
    assert person[0]["track_id"] != car_id
    assert update("car")[0]["track_id"] == car_id


def test_bytetrack_starts_a_track_at_half_confidence():
    from dashpi.vision import ByteTracker

    tracker = ByteTracker(10)
    frame = np.zeros((120, 120, 3), dtype=np.uint8)
    assert len(tracker.update(frame, [{"label": "car", "confidence": 0.5,
                                      "box": [20, 20, 60, 60]}], OverlaySettings())) == 1


def test_bytetrack_expires_paths_in_video_time_even_with_detection_gaps():
    from dashpi.vision import ByteTracker

    tracker = ByteTracker(10)
    for index in range(33):
        frame = np.zeros((120, 120, 3), dtype=np.uint8)
        x = 10 + index // 2
        detections = [{"label": "car", "confidence": 0.9, "box": [x, 20, x + 40, 60]}] if index % 8 == 0 else []
        tracked = tracker.update(frame, detections, OverlaySettings())
    path = tracker.traces.trace.get(tracked[0]["track_id"])
    assert len(path) == 3
    assert path[0, 0] == 38  # points older than two seconds have expired


def test_bytetrack_releases_expired_ids_without_reusing_them():
    from dashpi.vision import ByteTracker

    tracker = ByteTracker(10)
    frame = np.zeros((120, 120, 3), dtype=np.uint8)
    ids = []
    for _ in range(5):
        detections = [{"label": "car", "confidence": 0.9, "box": [20, 20, 60, 60]}]
        tracked = tracker.update(frame, detections, OverlaySettings())
        if not tracked:
            tracked = tracker.update(frame, detections, OverlaySettings())
        ids.append(tracked[0]["track_id"])
        for _ in range(15):
            tracker.update(frame, [], OverlaySettings())
    assert len(set(ids)) == 5
    assert not tracker.track_ids


def test_tracking_video_preserves_source_and_rejects_existing_destinations(tmp_path):
    from dashpi.vision import track_video
    from dashpi.storage import sha256_file
    from dashpi.media import probe_duration

    source = make_video(tmp_path / "source.mp4", 2)
    original = sha256_file(source)
    output = tmp_path / "tracked.mp4"
    detector = lambda _frame: [{"label": "car", "confidence": 0.9, "box": [10, 10, 70, 70]}]
    result = track_video(source, output, detector)
    assert result.path == output
    assert result.sha256 == sha256_file(output)
    assert probe_duration(output) == pytest.approx(2, abs=0.15)
    assert sha256_file(source) == original
    for destination in (source, output):
        with pytest.raises(FileExistsError):
            track_video(source, destination, detector)
    assert sha256_file(output) == result.sha256
    assert not list(tmp_path.glob(".dashpi-track-*"))


def test_tracking_labels_remain_readable_when_full_hd_is_exported_at_480p(tmp_path):
    from dashpi.vision import track_video

    source = tmp_path / "source.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                    "color=black:s=1920x1080:r=1:d=1", "-c:v", "libx264", str(source)], check=True)
    output = tmp_path / "tracked.mp4"
    track_video(source, output, lambda _frame: [
        {"label": "car", "confidence": 0.9, "box": [180, 400, 500, 700]}])
    capture = cv2.VideoCapture(str(output))
    ok, frame = capture.read()
    capture.release()
    assert ok
    label = frame[145:176, 75:225]
    assert np.count_nonzero(np.any(label > 40, axis=(1, 2))) >= 9


def test_tracking_does_not_replace_a_destination_created_while_processing(tmp_path):
    from dashpi.vision import track_video

    source = make_video(tmp_path / "source.mp4", 1)
    output = tmp_path / "tracked.mp4"
    def detector(_frame):
        if not output.exists():
            output.write_bytes(b"another process owns this file")
        return []

    with pytest.raises(FileExistsError):
        track_video(source, output, detector)
    assert output.read_bytes() == b"another process owns this file"
    assert not list(tmp_path.glob(".dashpi-track-*"))


def test_tracking_rejects_video_if_decoding_stops_early(tmp_path, monkeypatch):
    from dashpi.vision import track_video
    from dashpi.storage import sha256_file

    source = make_video(tmp_path / "source.mp4", 2)
    original = sha256_file(source)
    output = tmp_path / "tracked.mp4"
    capture = cv2.VideoCapture(str(source))

    class InterruptedCapture:
        def __init__(self):
            self.frames = 0

        def __getattr__(self, name):
            return getattr(capture, name)

        def read(self):
            self.frames += 1
            return capture.read() if self.frames <= 5 else (False, None)

    monkeypatch.setattr(cv2, "VideoCapture", lambda _path: InterruptedCapture())
    with pytest.raises(RuntimeError, match="incomplete"):
        track_video(source, output, lambda _frame: [])
    assert sha256_file(source) == original
    assert not output.exists()
    assert not list(tmp_path.glob(".dashpi-track-*"))


def test_yolo_detector_filters_coco_classes_and_maps_letterboxed_boxes(monkeypatch, tmp_path):
    class Net:
        def setInput(self, blob):
            self.blob = blob

        def forward(self):
            output = np.zeros((1, 84, 8400), dtype=np.float32)
            output[0, 0:4, 0] = [320, 320, 200, 200]
            output[0, 4 + 2, 0] = 0.9
            output[0, 0:4, 1] = [320, 320, 200, 200]
            output[0, 4 + 4, 1] = 0.95
            return output

    net = Net()
    monkeypatch.setattr(cv2.dnn, "readNetFromONNX", lambda _path: net)
    monkeypatch.setattr(cv2.dnn, "NMSBoxes", lambda _boxes, _scores, _threshold, _nms: [0])
    detector = YoloDetector(tmp_path / "model.onnx", confidence=0.5)

    assert detector(np.zeros((240, 320, 3), dtype=np.uint8)) == [
        {"label": "car", "confidence": 0.9, "box": [110, 70, 210, 170]}
    ]
