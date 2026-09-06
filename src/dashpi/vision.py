from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path
import subprocess

import cv2
import numpy as np

from dashpi.config import OverlaySettings
from dashpi.models import FileArtifact
from dashpi.storage import atomic_write, sha256_file


ROAD_USERS = {"person", "bicycle", "car", "motorcycle", "bus", "truck"}
ROAD_USER_COLORS = {
    "person": (80, 200, 120),
    "bicycle": (20, 180, 240),
    "car": (230, 170, 40),
    "motorcycle": (210, 110, 210),
    "bus": (200, 190, 40),
    "truck": (180, 120, 60),
}
COCO_LABELS = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
    "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog",
    "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
    "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite",
    "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket", "bottle",
    "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich",
    "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote",
    "keyboard", "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator", "book",
    "clock", "vase", "scissors", "teddy bear", "hair drier", "toothbrush",
]
DETECTABLE_LABELS = ROAD_USERS | {"traffic light", "stop sign"}


class YoloDetector:
    def __init__(self, model_path: Path, confidence: float = 0.45):
        self.net = cv2.dnn.readNetFromONNX(str(model_path))
        self.confidence = confidence

    def __call__(self, frame: np.ndarray) -> list[dict]:
        height, width = frame.shape[:2]
        scale = min(640 / width, 640 / height)
        resized_width, resized_height = round(width * scale), round(height * scale)
        letterboxed = np.zeros((640, 640, 3), dtype=np.uint8)
        pad_x, pad_y = (640 - resized_width) // 2, (640 - resized_height) // 2
        letterboxed[pad_y : pad_y + resized_height, pad_x : pad_x + resized_width] = cv2.resize(
            frame, (resized_width, resized_height)
        )
        blob = cv2.dnn.blobFromImage(
            letterboxed, scalefactor=1 / 255, size=(640, 640), swapRB=True, crop=False
        )
        self.net.setInput(blob)
        output = self.net.forward()
        if output.shape == (1, 84, 8400):
            predictions = output[0].T
        elif output.shape == (1, 8400, 84):
            predictions = output[0]
        else:
            raise ValueError("unsupported YOLOv8 output")

        boxes, scores, labels = [], [], []
        for prediction in predictions:
            class_index = int(np.argmax(prediction[4:]))
            confidence = float(prediction[4 + class_index])
            label = COCO_LABELS[class_index]
            if confidence < self.confidence or label not in DETECTABLE_LABELS:
                continue
            center_x, center_y, box_width, box_height = prediction[:4]
            x1 = int(round((center_x - box_width / 2 - pad_x) / scale))
            y1 = int(round((center_y - box_height / 2 - pad_y) / scale))
            x2 = int(round((center_x + box_width / 2 - pad_x) / scale))
            y2 = int(round((center_y + box_height / 2 - pad_y) / scale))
            x1, x2 = max(0, x1), min(width, x2)
            y1, y2 = max(0, y1), min(height, y2)
            if x2 <= x1 or y2 <= y1:
                continue
            boxes.append([x1, y1, x2 - x1, y2 - y1])
            scores.append(confidence)
            labels.append(label)
        if not boxes:
            return []
        indices = np.asarray(cv2.dnn.NMSBoxes(boxes, scores, self.confidence, 0.45)).reshape(-1)
        return [
            {
                "label": labels[index],
                "confidence": round(scores[index], 4),
                "box": [
                    boxes[index][0],
                    boxes[index][1],
                    boxes[index][0] + boxes[index][2],
                    boxes[index][1] + boxes[index][3],
                ],
            }
            for index in indices
        ]


def should_draw(label: str, overlays: OverlaySettings) -> bool:
    return (
        label in ROAD_USERS
        or (label == "traffic light" and overlays.traffic_lights)
        or (label == "stop sign" and overlays.traffic_signs)
    )


def box_iou(left: list[int], right: list[int]) -> float:
    x1, y1 = max(left[0], right[0]), max(left[1], right[1])
    x2, y2 = min(left[2], right[2]), min(left[3], right[3])
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    left_area = max(0, left[2] - left[0]) * max(0, left[3] - left[1])
    right_area = max(0, right[2] - right[0]) * max(0, right[3] - right[1])
    union = left_area + right_area - intersection
    return intersection / union if union else 0.0


def assign_track_ids(previous: list[dict], current: list[dict], next_id: int) -> tuple[list[dict], int]:
    assigned, used = [], set()
    for detection in current:
        matches = [
            item
            for item in previous
            if item["track_id"] not in used
            and item["label"] == detection["label"]
            and box_iou(item["box"], detection["box"]) >= 0.30
        ]
        if matches:
            track_id = max(matches, key=lambda item: box_iou(item["box"], detection["box"]))["track_id"]
        else:
            track_id, next_id = next_id, next_id + 1
        used.add(track_id)
        assigned.append({**detection, "track_id": track_id})
    return assigned, next_id


def lane_lines(frame: np.ndarray) -> list[tuple[int, int, int, int]]:
    grayscale = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(grayscale, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    height, width = edges.shape
    mask = np.zeros_like(edges)
    top = int(height * 0.55)
    cv2.fillPoly(mask, [np.array([(0, height), (width, height), (width, top), (0, top)])], 255)
    segments = cv2.HoughLinesP(cv2.bitwise_and(edges, mask), 1, np.pi / 180, 30, minLineLength=40, maxLineGap=20)
    if segments is None:
        return []
    lines = []
    for x1, y1, x2, y2 in segments[:, 0]:
        length = float(np.hypot(x2 - x1, y2 - y1))
        slope = abs((y2 - y1) / (x2 - x1)) if x2 != x1 else float("inf")
        if length >= 40 and slope >= 0.35:
            lines.append((int(x1), int(y1), int(x2), int(y2)))
    return lines


def draw_overlays(frame: np.ndarray, detections: list[dict], overlays: OverlaySettings) -> np.ndarray:
    detected_lanes = lane_lines(frame) if overlays.lanes else []
    relevant = max(
        (item for item in detections if item["label"] in ROAD_USERS),
        key=lambda item: (item["box"][2] - item["box"][0]) * (item["box"][3] - item["box"][1]),
        default=None,
    )
    for item in detections:
        if not should_draw(item["label"], overlays):
            continue
        color = (50, 50, 230) if item is relevant else ROAD_USER_COLORS.get(item["label"], (0, 190, 255))
        x1, y1, x2, y2 = item["box"]
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(
            frame,
            f'{item["label"]} #{item["track_id"]}',
            (x1, max(18, y1 - 5)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            1,
            cv2.LINE_AA,
        )
    for x1, y1, x2, y2 in detected_lanes:
        cv2.line(frame, (x1, y1), (x2, y2), (0, 190, 255), 3, cv2.LINE_AA)
    return frame


def annotate_clip(
    source: Path,
    output: Path,
    start: float,
    duration: float,
    incident_offset: float,
    detector: Callable[[np.ndarray], list[dict]],
    overlays: OverlaySettings,
    keyframe_dir: Path,
    output_height: int,
    bitrate: str,
) -> tuple[FileArtifact, list[dict], list[FileArtifact]]:
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        capture.release()
        raise RuntimeError("could not open source clip")
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    width, height = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(output.name + ".partial")
    process = subprocess.Popen(
        [
            "ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
            "-s", f"{width}x{height}", "-r", str(fps), "-i", "-", "-an", "-vf",
            f"scale=-2:{output_height}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-b:v",
            bitrate, "-movflags", "+faststart", "-f", "mp4", str(partial),
        ],
        stdin=subprocess.PIPE,
    )
    targets = [
        ("before.jpg", max(0.0, incident_offset - start - 2.0)),
        ("moment.jpg", incident_offset - start),
        ("after.jpg", min(duration - 0.001, incident_offset - start + 2.0)),
    ]
    nearest: dict[str, tuple[float, np.ndarray] | None] = {name: None for name, _target in targets}
    observations, previous, next_id, frame_index = [], [], 1, 0
    try:
        capture.set(cv2.CAP_PROP_POS_MSEC, start * 1000)
        while frame_index / fps < duration:
            ok, frame = capture.read()
            if not ok:
                break
            source_seconds = start + frame_index / fps
            current = [
                {
                    "label": item["label"],
                    "confidence": float(item["confidence"]),
                    "box": [int(value) for value in item["box"]],
                }
                for item in detector(frame)
            ]
            tracked, next_id = assign_track_ids(previous, current, next_id)
            observations.extend(
                {
                    "timestamp": round(source_seconds, 3),
                    "track_id": item["track_id"],
                    "label": item["label"],
                    "confidence": round(item["confidence"], 4),
                    "box": item["box"],
                }
                for item in tracked
            )
            annotated = draw_overlays(frame, tracked, overlays)
            for name, target in targets:
                candidate = nearest[name]
                difference = abs(frame_index / fps - target)
                if candidate is None or difference < candidate[0]:
                    nearest[name] = (difference, annotated.copy())
            if process.stdin is None:
                raise RuntimeError("ffmpeg stdin unavailable")
            process.stdin.write(annotated.tobytes())
            previous, frame_index = tracked, frame_index + 1
        if process.stdin is not None and not process.stdin.closed:
            process.stdin.close()
        if process.wait() != 0:
            raise RuntimeError("ffmpeg failed")
    finally:
        capture.release()
        if process.stdin is not None and not process.stdin.closed:
            process.stdin.close()
        if process.poll() is None:
            process.wait()
    if any(frame is None for frame in nearest.values()):
        raise RuntimeError("could not create all keyframes")
    keyframes = []
    for name, _target in targets:
        _difference, image = nearest[name]  # type: ignore[misc]
        encoded, data = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 88])
        if not encoded:
            raise RuntimeError("could not encode keyframe")
        keyframes.append(atomic_write(keyframe_dir / name, data.tobytes()))
    with partial.open("rb") as completed:
        completed.flush()
        os.fsync(completed.fileno())
    artifact = FileArtifact(output, partial.stat().st_size, sha256_file(partial))
    partial.replace(output)
    return artifact, observations, keyframes
