import cv2
import numpy as np

from dashpi.config import OverlaySettings
from dashpi.vision import YoloDetector, annotate_clip, assign_track_ids, draw_overlays

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
    )
    assert calls
    assert {item["label"] for item in observations} == {"car", "traffic light"}
    assert len(keyframes) == 3
    assert artifact.path.exists()


def test_iou_tracking_keeps_id_for_overlapping_detection():
    previous = [{"track_id": 7, "label": "car", "box": [10, 10, 50, 50]}]
    current = [{"label": "car", "confidence": 0.9, "box": [12, 12, 52, 52]}]
    assert assign_track_ids(previous, current, next_id=8)[0][0]["track_id"] == 7


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
