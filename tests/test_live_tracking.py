import numpy as np
import pytest

from dashpi.live_tracking import LiveTracker, render_overlay, track_color


def detection(label='car', confidence=.9, box=None):
    return dict(label=label, confidence=confidence, box=box or [10, 10, 70, 70])


def test_low_confidence_keeps_existing_id():
    tracker = LiveTracker()
    first = tracker.update([dict(label='car', confidence=.9, box=[10,10,70,70])])
    second = tracker.update([dict(label='car', confidence=.9, box=[11,10,71,70])])
    low = tracker.update([dict(label='car', confidence=.2, box=[12,10,72,70])])
    assert first[0]['track_id'] == second[0]['track_id'] == low[0]['track_id']
    assert low[0]['confidence'] == .2
    assert low[0]['box'] == [12, 10, 72, 70]


def test_classes_have_distinct_visible_ids():
    tracker = LiveTracker()
    result = tracker.update([detection('car'), detection('person')])
    assert len({item['track_id'] for item in result}) == 2
    assert {item['label'] for item in result} == {'car', 'person'}
    again = tracker.update([detection('person'), detection('car')])
    assert {item['label']: item['track_id'] for item in result} == {
        item['label']: item['track_id'] for item in again
    }


def test_empty_frames_age_out_tracks():
    tracker = LiveTracker()
    old = tracker.update([detection()])[0]['track_id']
    for _ in range(12):
        assert tracker.update([]) == []
    tracker.update([detection()])
    new = tracker.update([detection()])[0]['track_id']
    assert new != old


def test_low_confidence_does_not_create_track_and_non_road_users_filtered():
    assert LiveTracker().update([detection(confidence=.2), detection('airplane')]) == []


@pytest.mark.parametrize('frame_rate', [0, -1, float('inf'), float('nan')])
def test_invalid_frame_rate(frame_rate):
    with pytest.raises(ValueError):
        LiveTracker(frame_rate=frame_rate)


@pytest.mark.parametrize('threshold', [0, -1, 1, float('inf'), float('nan')])
def test_invalid_threshold(threshold):
    with pytest.raises(ValueError):
        LiveTracker(activation_threshold=threshold)


def test_colors_and_transparent_overlay_coordinates():
    assert track_color(7) == track_color(7)
    assert track_color(7) != track_color(8)
    empty = render_overlay(160, 90, [])
    assert empty.shape == (90, 160, 4)
    assert empty.dtype == np.uint8
    assert not empty.any()
    result = render_overlay(160, 90, [{**detection(box=[30, 30, 100, 70]), 'track_id': 7}])
    assert tuple(result[50, 30]) == (*track_color(7), 255)
    assert result[50, 60, 3] == 0
    assert result[80, 140, 3] == 0
    bounded = render_overlay(160, 90, [{**detection(box=[-10, 30, 180, 100]), 'track_id': 7}])
    assert bounded[50, 0, 3] == 255
    assert bounded[89, 100, 3] == 255


def test_module_import_without_optional_dependency():
    import subprocess
    import sys

    script = '''
import importlib.abc
import sys
class BlockSupervision(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'supervision':
            raise ModuleNotFoundError('supervision unavailable')
sys.meta_path.insert(0, BlockSupervision())
from dashpi.vision import YoloDetector
from dashpi.live_tracking import LiveTracker, render_overlay
assert render_overlay(10, 10, []).shape == (10, 10, 4)
try:
    LiveTracker()
except RuntimeError as exc:
    assert 'dashpi[tracking]' in str(exc)
else:
    raise AssertionError('missing dependency was not reported')
'''
    subprocess.run([sys.executable, '-c', f'import sys; sys.path = {sys.path!r}\n' + script], check=True)


def test_worker_stop_discards_slow_inference_result():
    import threading
    import time
    from dashpi.live_tracking import TrackingWorker
    entered, finish = threading.Event(), threading.Event()
    def detector(frame):
        entered.set()
        finish.wait(2)
        return []
    class Tracker:
        def update(self, detections):
            return detections
    worker = TrackingWorker(lambda stop: np.zeros((360, 640, 3), dtype=np.uint8),
                            detector, Tracker(), 10)
    worker.start()
    assert entered.wait(1)
    stopping = threading.Thread(target=worker.stop)
    stopping.start()
    time.sleep(.02)
    assert stopping.is_alive()
    finish.set()
    stopping.join(1)
    assert not stopping.is_alive()
    assert worker.snapshot() == (None, None)
    assert not worker.thread.is_alive()


def test_worker_inference_failure_is_reported_without_result():
    from dashpi.live_tracking import TrackingWorker
    def fail(frame):
        raise ValueError('inference failed')
    worker = TrackingWorker(lambda stop: np.zeros((1, 1, 3), dtype=np.uint8), fail,
                            LiveTracker())
    worker.start()
    worker.thread.join(1)
    assert not worker.thread.is_alive()
    assert worker.snapshot() == (None, 'inference failed')
    worker.stop()


@pytest.mark.parametrize('fps', [0, -1, 11, float('nan'), float('inf')])
def test_worker_enforces_finite_ten_hz_maximum(fps):
    from dashpi.live_tracking import TrackingWorker
    with pytest.raises(ValueError):
        TrackingWorker(None, None, None, fps)
