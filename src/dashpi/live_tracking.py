"""Optional ByteTrack engine and preview RGBA rendering.

Boxes use pixel xyxy coordinates in the supplied overlay's coordinate space.
"""
from __future__ import annotations

import colorsys
import math

import cv2
import numpy as np

from dashpi.vision import COCO_LABELS, ROAD_USERS


class LiveTracker:
    def __init__(self, frame_rate=10, activation_threshold=0.45):
        if not math.isfinite(frame_rate) or frame_rate <= 0:
            raise ValueError('frame_rate must be finite and positive')
        if not math.isfinite(activation_threshold) or not 0 < activation_threshold < 1:
            raise ValueError('activation_threshold must be finite and between 0 and 1')
        try:
            import supervision as sv
        except ImportError as exc:
            raise RuntimeError('Live tracking requires the dashpi[tracking] extra') from exc
        self._sv = sv
        self._trackers = {
            label: sv.ByteTrack(
                frame_rate=frame_rate,
                track_activation_threshold=activation_threshold,
            )
            for label in sorted(ROAD_USERS)
        }

    def update(self, detections: list[dict]) -> list[dict]:
        result = []
        for label, tracker in self._trackers.items():
            current = [item for item in detections if item['label'] == label]
            class_id = COCO_LABELS.index(label)
            inputs = self._sv.Detections(
                xyxy=np.asarray([item['box'] for item in current], dtype=float).reshape(-1, 4),
                confidence=np.asarray([item['confidence'] for item in current], dtype=float),
                class_id=np.full(len(current), class_id, dtype=int),
                data={'source_index': np.arange(len(current))},
            )
            tracked = tracker.update_with_detections(inputs)
            for index, local_id in zip(tracked.data.get('source_index', []), tracked.tracker_id):
                # Each class owns a disjoint residue, including after tracks expire.
                visible_id = (int(local_id) - 1) * len(COCO_LABELS) + class_id + 1
                result.append({**current[int(index)], 'track_id': visible_id})
        return result


def track_color(track_id: int) -> tuple[int, int, int]:
    """Return a deterministic RGB color for a session's visible ID."""
    rgb = colorsys.hsv_to_rgb((track_id * 0.618033988749895) % 1, .75, 1)
    return tuple(round(value * 255) for value in rgb)


def render_overlay(width: int, height: int, detections: list[dict]) -> np.ndarray:
    """Draw preview-only boxes; caller maps frame coordinates to this size."""
    overlay = np.zeros((height, width, 4), dtype=np.uint8)
    for item in detections:
        x1, y1, x2, y2 = (round(value) for value in item['box'])
        if x2 <= 0 or y2 <= 0 or x1 >= width or y1 >= height:
            continue
        x1, x2 = max(0, x1), min(width - 1, x2)
        y1, y2 = max(0, y1), min(height - 1, y2)
        if x2 <= x1 or y2 <= y1:
            continue
        color = (*track_color(item['track_id']), 255)
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 2)
        cv2.putText(
            overlay, f"{item['label']} #{item['track_id']}",
            (x1, max(14, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX,
            .45, color, 1, cv2.LINE_AA,
        )
    return overlay


class TrackingWorker:
    """One capture/inference thread and a replaceable, timestamped result slot."""

    def __init__(self, read_frame, detector, tracker, fps=10):
        import threading
        self.read_frame, self.detector, self.tracker = read_frame, detector, tracker
        self.interval = 1 / fps
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.result = self.error = None
        self.thread = threading.Thread(target=self._run, name='dashpi-tracking', daemon=True)

    def start(self):
        self.thread.start()

    def snapshot(self):
        with self.lock:
            return self.result, self.error

    def stop(self):
        self.stop_event.set()
        self.thread.join()
        with self.lock:
            self.result = self.error = None

    def _run(self):
        import time
        try:
            while not self.stop_event.is_set():
                started = time.monotonic()
                frame = self.read_frame(self.stop_event)
                if frame is None or self.stop_event.is_set():
                    break
                captured = time.monotonic()
                tracks = self.tracker.update(self.detector(frame))
                with self.lock:
                    if not self.stop_event.is_set():
                        self.result = (captured, frame.shape[:2], tracks)
                self.stop_event.wait(max(0, self.interval - (time.monotonic() - started)))
        except Exception as error:
            with self.lock:
                if not self.stop_event.is_set():
                    self.error = str(error)
                    self.result = None
