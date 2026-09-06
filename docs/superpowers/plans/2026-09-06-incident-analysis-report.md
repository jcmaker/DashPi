# Incident Analysis Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 승인된 45초 증거 보존 흐름 위에 사고 시점 중심 10초 추적 영상, 시각적 자급형 HTML/PDF 리포트, 기존 광학 전송을 완성한다.

**Architecture:** 기존 `IncidentPipeline`이 45초 `clip.mp4`를 그대로 보존하고, Ollama 결과에서 사고 시점을 검증한 뒤 OpenCV/FFmpeg로 별도 `annotated.mp4`와 핵심 장면 3장을 만든다. `report.html`은 영상과 이미지를 data URL로 포함하며 기존 `DPC1`/`DPQ1` 광학 계층에는 변경 없이 단일 파일로 전달된다. 분석은 단일 백그라운드 작업자로 실행해 녹화 호출 경로를 막지 않는다.

**Tech Stack:** Python 3.11+, OpenCV DNN, FFmpeg/ffprobe, FastAPI, 표준 HTML/CSS/JavaScript, pytest, 기존 DashPi Optical v1

## Global Constraints

- `clip.mp4`는 트리거 이전 30초와 이후 15초를 담은 오버레이 없는 불변 증거 파일이다.
- 파생 영상은 검증된 사고 시점 이전 5초와 이후 5초를 담으며, 증거 영상이 10초 이상이면 경계에서도 정확히 10초를 유지한다.
- 차량·오토바이·자전거·보행자는 항상 표시하고, 신호등·차선·표지판은 각각 독립 설정하며 기본값은 모두 OFF다.
- 오버레이 설정은 렌더링에만 영향을 주며 Ollama 입력과 객체 탐지 범위를 줄이지 않는다.
- 모든 완성 artifact는 `.partial` 쓰기 → flush/fsync → SHA-256 → atomic rename → metadata 저장 순서를 지킨다.
- 초기 파생 영상은 H.264 480p/900 kbit/s, 초과 시 H.264 360p/450 kbit/s로 한 번만 낮춘다.
- 광학 payload는 기존 `MAX_PAYLOAD == 16 * 1024 * 1024` 이하일 때만 전송하며 `DPC1`/`DPQ1` wire format은 변경하지 않는다.
- 추적 실패는 박스 없는 10초 영상과 경고가 있는 유효한 리포트를 만들고, 사고 시점 또는 AI 리포트 실패는 `analysis_failed`로 남긴다.
- HTML은 오프라인 단일 파일이며 HTML 다운로드와 브라우저 기본 인쇄 기반 PDF 저장을 제공한다. 인쇄에는 영상 대신 핵심 장면 3장을 넣는다.
- 광학 전송은 분석 완료 후 자동 시작하지 않으며 사용자가 정차 확인 뒤 직접 시작한다.
- 수신 결과는 기존 전체 길이 및 SHA-256 검증을 통과하기 전에는 열거나 저장하지 않는다.
- Decimen Optical Transfer의 소스, wire bytes, golden vector, decoder artifact를 복사하지 않는다.
- 법적 과실 판단, 자동 충돌 감지, 클라우드, 네이티브 앱, Raspberry Pi PDF 생성, 오디오 추가는 이 계획 밖이다.

---

## File Map

- `pyproject.toml` — OpenCV 런타임 의존성만 추가한다.
- `src/dashpi/config.py` — detector 경로, 신뢰도, 세 가지 선택 오버레이 설정을 검증한다.
- `src/dashpi/models.py` — `annotated.mp4`와 사고 시점 offset을 metadata artifact 계약에 추가한다.
- `src/dashpi/storage.py` — 새 metadata 필드를 이전 파일과 호환되게 역직렬화한다.
- `src/dashpi/media.py` — 10초 경계 계산, H.264 파생 영상 인코딩, 핵심 프레임 추출을 맡는다.
- `src/dashpi/vision.py` — 설치 제공 YOLOv8 COCO ONNX 탐지, 짧은 IoU 추적, 선택 오버레이 렌더링을 맡는 유일한 새 production 모듈이다.
- `src/dashpi/reports.py` — 사고 시점이 포함된 Ollama 응답 검증과 시각적 self-contained HTML 생성을 맡는다.
- `src/dashpi/pipeline.py` — 기존 clip 생성 뒤 분석·추적·fallback·크기 축소·artifact 저장 순서를 조립한다.
- `src/dashpi/api.py` — 재생성 설정과 광학 가능 여부를 노출하되 기존 광학 session 코드는 재사용한다.
- `src/dashpi/analysis_worker.py` — 분석 하나만 백그라운드에서 실행하고 녹화 압력 동안 단계 사이에서 대기한다.
- `src/dashpi/cli.py`, `src/dashpi/server.py` — 설치 설정과 production detector/worker를 조립한다.
- `src/dashpi/web/index.html`, `src/dashpi/web/tokens.css` — 오버레이 설정, 수동 시점 재시도, 정차 후 전송 진입 UI를 제공한다.
- `web/public/sender.html`, `src/dashpi/web/sender.html` — 전송 전 정차·비밀성 확인 문구를 제공한다.
- `web/public/receiver.html`, `src/dashpi/web/receiver.html` — 검증된 HTML 안의 다운로드/인쇄 스크립트만 sandbox에서 허용한다.
- `web/tests/sender.test.ts` — 사용자가 누를 때만 report 전송을 시작하는 기존 동작을 회귀 검증한다.
- `tests/` — 각 변경 모듈의 최소 실패 테스트와 전체 오프라인 E2E를 둔다.

### Task 1: Overlay Settings and Artifact Metadata

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/dashpi/config.py`
- Modify: `src/dashpi/models.py`
- Modify: `src/dashpi/storage.py`
- Modify: `src/dashpi/cli.py`
- Test: `tests/test_config.py`
- Test: `tests/test_models.py`
- Test: `tests/test_storage.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: 기존 `Settings`, `IncidentMetadata`, `FileArtifact`, `IncidentStore`
- Produces: `OverlaySettings`, `Settings.detector_model`, `Settings.detection_confidence`, `IncidentMetadata.annotated`, `IncidentMetadata.incident_offset_seconds`

- [ ] **Step 1: 새 기본값과 metadata round-trip 실패 테스트를 작성한다**

```python
# tests/test_config.py
from dashpi.config import OverlaySettings

def test_optional_overlays_default_off_and_are_independent(tmp_path):
    settings = Settings(tmp_path, "test-model")
    assert settings.overlays == OverlaySettings(False, False, False)
    assert settings.detector_model is None
    assert settings.detection_confidence == 0.45
    custom = OverlaySettings(traffic_lights=True, lanes=False, traffic_signs=True)
    assert custom.to_dict() == {
        "traffic_lights": True,
        "lanes": False,
        "traffic_signs": True,
    }

def test_detection_confidence_is_a_probability(tmp_path):
    with pytest.raises(ValueError, match="detection_confidence"):
        Settings(tmp_path, "test-model", detection_confidence=1.1)
```

```python
# tests/test_models.py
def test_incident_metadata_serializes_derived_artifact_and_localized_time(tmp_path):
    item = IncidentMetadata.new("inc-1", "2026-09-06T00:00:00Z", 40.0, 15.0)
    item.annotated = FileArtifact(tmp_path / "annotated.mp4", 3, "abc", 10.0)
    item.incident_offset_seconds = 29.5
    raw = item.to_dict()
    assert raw["annotated"]["filename"] == "annotated.mp4"
    assert raw["incident_offset_seconds"] == 29.5
```

```python
# tests/test_storage.py
def test_store_round_trips_derived_artifact_and_overlay_era_fields(tmp_path):
    store = IncidentStore(tmp_path)
    item = IncidentMetadata.new("inc-1", "2026-09-06T00:00:00Z", 40.0, 15.0)
    item.annotated = atomic_write(store.directory("inc-1") / "annotated.mp4", b"mp4")
    item.incident_offset_seconds = 30.0
    store.save(item)
    loaded = store.load("inc-1")
    assert loaded.annotated == item.annotated
    assert loaded.incident_offset_seconds == 30.0

def test_store_loads_metadata_written_before_derived_fields(tmp_path):
    store = IncidentStore(tmp_path)
    item = IncidentMetadata.new("inc-old", "2026-09-02T00:00:00Z", 40.0, 15.0)
    store.save(item)
    path = store.directory("inc-old") / "metadata.json"
    raw = json.loads(path.read_text())
    raw.pop("annotated", None)
    raw.pop("incident_offset_seconds", None)
    path.write_text(json.dumps(raw))
    loaded = store.load("inc-old")
    assert loaded.annotated is None and loaded.incident_offset_seconds is None
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_config.py tests/test_models.py tests/test_storage.py -q`

Expected: FAIL with `ImportError: cannot import name 'OverlaySettings'` or missing `annotated` field.

- [ ] **Step 3: 최소 설정·metadata 계약을 추가한다**

```python
# src/dashpi/config.py
from dataclasses import dataclass, field

@dataclass(frozen=True)
class OverlaySettings:
    traffic_lights: bool = False
    lanes: bool = False
    traffic_signs: bool = False

    def to_dict(self) -> dict[str, bool]:
        return {
            "traffic_lights": self.traffic_lights,
            "lanes": self.lanes,
            "traffic_signs": self.traffic_signs,
        }

@dataclass(frozen=True)
class Settings:
    data_root: Path
    ollama_model: str
    segment_seconds: float = 2.0
    pre_seconds: float = 30.0
    post_seconds: float = 15.0
    frame_sample_count: int = 12
    raw_max_fraction: float = 0.70
    min_free_fraction: float = 0.10
    detector_model: Path | None = None
    detection_confidence: float = 0.45
    overlays: OverlaySettings = field(default_factory=OverlaySettings)

    def __post_init__(self) -> None:
        if not self.ollama_model.strip():
            raise ValueError("ollama_model is required")
        if min(self.segment_seconds, self.pre_seconds, self.post_seconds) <= 0:
            raise ValueError("recording durations must be positive")
        if not 0.0 < self.detection_confidence <= 1.0:
            raise ValueError("detection_confidence must be in (0, 1]")
```

```python
# src/dashpi/models.py — IncidentMetadata의 artifact 필드 옆
annotated: FileArtifact | None = None
incident_offset_seconds: float | None = None

# IncidentMetadata.to_dict의 artifact loop
for key in ("clip", "annotated", "report_json", "report_html"):
    artifact = getattr(self, key)
    if artifact:
        data[key] = {
            "filename": artifact.path.name,
            "path": str(artifact.path),
            "byte_length": artifact.byte_length,
            "sha256": artifact.sha256,
            "duration": artifact.duration,
        }

# IncidentStore._metadata_from_raw의 호환 기본값
raw.setdefault("annotated", None)
raw.setdefault("incident_offset_seconds", None)

# IncidentStore._metadata_from_raw의 artifact loop
for key in ("clip", "annotated", "report_json", "report_html"):
    if raw.get(key):
        raw[key] = FileArtifact(
            Path(raw[key]["path"]),
            raw[key]["byte_length"],
            raw[key]["sha256"],
            raw[key].get("duration"),
        )
```

`pyproject.toml`의 runtime dependencies는 기존 두 항목에 `opencv-python-headless>=4.12,<5`만 추가한다. NumPy는 OpenCV가 제공하는 transitive dependency를 사용하고 별도 패키지나 inference service를 추가하지 않는다.

- [ ] **Step 4: CLI 플래그가 설정으로 전달되는 테스트와 구현을 추가한다**

```python
# tests/test_cli.py
def test_cli_accepts_detector_and_independent_overlay_flags(tmp_path):
    args = build_parser().parse_args([
        "simulate", "input.mp4", "--trigger-seconds", "40",
        "--data-root", str(tmp_path), "--ollama-model", "m",
        "--detector-model", "yolov8n.onnx", "--show-traffic-lights",
        "--show-traffic-signs",
    ])
    assert args.detector_model == Path("yolov8n.onnx")
    assert args.show_traffic_lights is True
    assert args.show_lanes is False
    assert args.show_traffic_signs is True
```

```python
# src/dashpi/cli.py — simulate parser
simulate.add_argument("--detector-model", type=Path)
simulate.add_argument("--detection-confidence", type=float, default=0.45)
simulate.add_argument("--show-traffic-lights", action="store_true")
simulate.add_argument("--show-lanes", action="store_true")
simulate.add_argument("--show-traffic-signs", action="store_true")
```

`main()`은 다음과 같이 설정을 한 번만 조립한다.

```python
settings = Settings(
    args.data_root,
    args.ollama_model,
    detector_model=args.detector_model,
    detection_confidence=args.detection_confidence,
    overlays=OverlaySettings(
        args.show_traffic_lights,
        args.show_lanes,
        args.show_traffic_signs,
    ),
)
```

- [ ] **Step 5: focused test와 전체 회귀 테스트를 통과시킨다**

Run: `python3 -m pytest tests/test_config.py tests/test_models.py tests/test_storage.py tests/test_cli.py -q && python3 -m pytest -q`

Expected: 모든 테스트 PASS.

- [ ] **Step 6: 커밋한다**

```bash
git add pyproject.toml src/dashpi/config.py src/dashpi/models.py src/dashpi/storage.py src/dashpi/cli.py tests/test_config.py tests/test_models.py tests/test_storage.py tests/test_cli.py
git commit -m "feat: configure incident report overlays"
```

### Task 2: Incident Localization and Ten-Second Media Window

**Files:**
- Modify: `src/dashpi/reports.py`
- Modify: `src/dashpi/media.py`
- Test: `tests/test_reports.py`
- Test: `tests/test_media.py`

**Interfaces:**
- Consumes: 12개 기존 sample frame, Ollama JSON, 증거 영상 길이
- Produces: `validate_report(raw: object, clip_sha256: str, model: str, generated_at: str, clip_duration: float, incident_offset_override: float | None = None) -> dict`, `transfer_window(incident_offset: float, evidence_duration: float) -> tuple[float, float]`, `transcode_clip(source: Path, output: Path, start: float, duration: float, height: int, bitrate: str) -> FileArtifact`, `extract_frame(source: Path, output: Path, timestamp: float) -> FileArtifact`

- [ ] **Step 1: 사고 시점 검증과 경계 계산 실패 테스트를 작성한다**

```python
# tests/test_reports.py
def test_report_requires_finite_incident_offset_inside_clip():
    report = validate_report(
        {"incident_timestamp": 22.4, "summary": "충돌", "observations": [], "limitations": []},
        "abc", "model", "now", clip_duration=45.0,
    )
    assert report["incident_timestamp"] == 22.4

@pytest.mark.parametrize("value", [-0.1, 45.1, True, float("nan")])
def test_report_rejects_invalid_incident_offset(value):
    with pytest.raises(ValueError, match="incident timestamp"):
        validate_report(
            {"incident_timestamp": value, "summary": "x", "observations": [], "limitations": []},
            "abc", "model", "now", clip_duration=45.0,
        )

def test_manual_offset_replaces_failed_localization_but_not_analysis_text():
    report = validate_report(
        {"summary": "충돌", "observations": [], "limitations": ["자동 시점 탐색 실패"]},
        "abc", "model", "now", clip_duration=45.0, incident_offset_override=7.0,
    )
    assert report["incident_timestamp"] == 7.0
```

```python
# tests/test_media.py
@pytest.mark.parametrize(
    ("incident", "expected"),
    [(22.5, (17.5, 27.5)), (2.0, (0.0, 10.0)), (44.0, (35.0, 45.0))],
)
def test_transfer_window_keeps_ten_seconds_at_boundaries(incident, expected):
    assert transfer_window(incident, 45.0) == expected

def test_transfer_window_uses_all_short_evidence():
    assert transfer_window(3.0, 8.0) == (0.0, 8.0)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_reports.py tests/test_media.py -q`

Expected: FAIL because `validate_report` lacks the new contract and `transfer_window` is undefined.

- [ ] **Step 3: trust-boundary validation과 구간 계산을 구현한다**

```python
# src/dashpi/media.py
def transfer_window(incident_offset: float, evidence_duration: float) -> tuple[float, float]:
    if not math.isfinite(incident_offset) or not 0.0 <= incident_offset <= evidence_duration:
        raise ValueError("incident timestamp outside evidence clip")
    duration = min(10.0, evidence_duration)
    start = min(max(0.0, incident_offset - 5.0), evidence_duration - duration)
    return start, start + duration
```

`validate_report`는 model root의 허용 키를 `summary`, `observations`, `limitations`, 선택적인 `incident_timestamp`로 제한한다. override가 없으면 `incident_timestamp`가 반드시 유한한 `int|float`이고 `0 <= value <= clip_duration`이어야 한다. override가 있으면 같은 범위 검증 뒤 그 값을 사용하며, bool은 숫자로 인정하지 않는다. 기존 observation·문자열·surplus-key 검증은 유지한다.

기존 `tests/test_reports.py`, `tests/test_pipeline.py`, `tests/test_offline_e2e.py`의 정상 analyzer fixture에는 모두 실제 clip 범위 안의 `"incident_timestamp": 3.0`을 추가한다. timestamp validation 자체를 검사하지 않는 기존 `validate_report` 호출에도 `clip_duration=6.0`을 명시한다.

Ollama prompt는 다음 exact sentence를 사용한다.

```python
"Return JSON with incident_timestamp (seconds from first frame), summary, observations, and limitations. Describe evidence only; do not determine legal fault."
```

- [ ] **Step 4: atomic H.264 transcode와 단일 프레임 추출 실패 테스트를 작성한다**

```python
# tests/test_media.py
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
```

- [ ] **Step 5: 기존 subprocess 패턴으로 media 함수를 구현한다**

`transcode_clip(source, output, start, duration, height, bitrate)`는 `build_clip`과 같은 partial/fsync/hash/replace 순서를 사용하고 다음 FFmpeg 옵션을 고정한다.

```python
[
    "ffmpeg", "-loglevel", "error", "-y", "-ss", str(start), "-i", str(source),
    "-t", str(duration), "-an", "-vf", f"scale=-2:{height}",
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-b:v", bitrate,
    "-movflags", "+faststart", "-f", "mp4", str(partial),
]
```

`extract_frame(source, output, timestamp)`는 `-ss`, `-frames:v 1`, `-q:v 2`, `-f image2`로 `.jpg.partial`을 만들고 `atomic_write`와 동일한 completion 순서를 적용한다. `transcode_clip`은 결과 길이가 요청보다 0.1초 이상 짧으면 실패시킨다.

- [ ] **Step 6: focused test와 회귀 테스트를 통과시킨다**

Run: `python3 -m pytest tests/test_reports.py tests/test_media.py -q && python3 -m pytest -q`

Expected: 모든 테스트 PASS.

- [ ] **Step 7: 커밋한다**

```bash
git add src/dashpi/reports.py src/dashpi/media.py tests/test_reports.py tests/test_media.py
git commit -m "feat: localize incident media window"
```

### Task 3: One-Pass Detection, Tracking, and Selective Overlays

**Files:**
- Create: `src/dashpi/vision.py`
- Create: `tests/test_vision.py`

**Interfaces:**
- Consumes: YOLOv8 COCO ONNX path, source clip, transfer start/duration, `OverlaySettings`
- Produces: `YoloDetector.__call__(frame) -> list[dict]`, `draw_overlays(frame, detections: list[dict], overlays: OverlaySettings)`, `annotate_clip(source: Path, output: Path, start: float, duration: float, incident_offset: float, detector: Callable, overlays: OverlaySettings, keyframe_dir: Path, output_height: int, bitrate: str) -> tuple[FileArtifact, list[dict], list[FileArtifact]]`

- [ ] **Step 1: class filtering과 선택 layer 실패 테스트를 작성한다**

```python
# tests/test_vision.py
import cv2
import numpy as np
from dashpi.config import OverlaySettings
from dashpi.vision import draw_overlays

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
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_vision.py -q`

Expected: FAIL with `ModuleNotFoundError: dashpi.vision`.

- [ ] **Step 3: detector output과 overlay policy를 최소 구현한다**

`YoloDetector`는 `cv2.dnn.readNetFromONNX(model_path)`를 생성 시 한 번 호출한다. 입력은 640×640 letterbox, RGB, `1/255` scale이며 `[1,84,8400]` 또는 `[1,8400,84]` YOLOv8 COCO output만 허용한다. `person`, `bicycle`, `car`, `motorcycle`, `bus`, `truck`, `traffic light`, `stop sign`만 confidence threshold 뒤 `cv2.dnn.NMSBoxes(boxes, scores, self.confidence, 0.45)`로 반환한다. 지원하지 않는 shape은 `ValueError("unsupported YOLOv8 output")`로 실패시킨다.

```python
# src/dashpi/vision.py
ROAD_USERS = {"person", "bicycle", "car", "motorcycle", "bus", "truck"}
ROAD_USER_COLORS = {
    "person": (80, 200, 120),
    "bicycle": (20, 180, 240),
    "car": (230, 170, 40),
    "motorcycle": (210, 110, 210),
    "bus": (200, 190, 40),
    "truck": (180, 120, 60),
}

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
            item for item in previous
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

def draw_overlays(frame, detections: list[dict], overlays: OverlaySettings):
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
        cv2.putText(frame, f'{item["label"]} #{item["track_id"]}', (x1, max(18, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, .5, color, 1, cv2.LINE_AA)
    for x1, y1, x2, y2 in detected_lanes:
        cv2.line(frame, (x1, y1), (x2, y2), (0, 190, 255), 3, cv2.LINE_AA)
    return frame
```

`lane_lines`는 grayscale → Gaussian blur → Canny → 하단 45% ROI → `HoughLinesP`를 사용하고, 길이 40px 미만 또는 기울기 절댓값 0.35 미만 선을 버린다. 선이 없으면 빈 list를 반환해 무리하게 차선을 그리지 않는다.

현재 frame에서 면적이 가장 큰 road user를 사고 관련 후보로 보고 빨간색으로 강조한다. 나머지는 label별 고정 색과 텍스트를 함께 사용해 색만으로 객체를 구분하지 않는다.

- [ ] **Step 4: 짧은 IoU track과 실제 video render 실패 테스트를 작성한다**

```python
def test_annotation_uses_detector_for_all_categories_but_hides_optional_boxes(tmp_path):
    source = make_video(tmp_path / "source.mp4", 2)
    calls = []
    def detector(frame):
        calls.append(frame.shape)
        return [
            {"label": "car", "confidence": .9, "box": [10, 10, 60, 60]},
            {"label": "traffic light", "confidence": .8, "box": [70, 5, 90, 40]},
        ]
    artifact, observations, keyframes = annotate_clip(
        source, tmp_path / "annotated.mp4", 0.0, 2.0, 1.0,
        detector, OverlaySettings(), tmp_path / "keyframes", 480, "900k",
    )
    assert calls
    assert {item["label"] for item in observations} == {"car", "traffic light"}
    assert len(keyframes) == 3
    assert artifact.path.exists()

def test_iou_tracking_keeps_id_for_overlapping_detection():
    previous = [{"track_id": 7, "label": "car", "box": [10, 10, 50, 50]}]
    current = [{"label": "car", "confidence": .9, "box": [12, 12, 52, 52]}]
    assert assign_track_ids(previous, current, next_id=8)[0][0]["track_id"] == 7
```

- [ ] **Step 5: 한 detection pass로 영상·관찰·핵심 장면을 만든다**

`annotate_clip`은 OpenCV로 `[start, start + duration]` 프레임을 순서대로 읽고 detector를 프레임당 정확히 한 번 호출한다. 같은 label이면서 IoU ≥ 0.30인 직전 프레임 box에 같은 증가형 `track_id`를 부여한다. 모든 detection을 다음 JSON-safe shape로 누적한다.

```python
{
    "timestamp": round(source_seconds, 3),
    "track_id": track_id,
    "label": label,
    "confidence": round(confidence, 4),
    "box": [x1, y1, x2, y2],
}
```

렌더 프레임은 stdin raw BGR로 다음 FFmpeg process에 쓰며 `annotated.mp4.partial`을 H.264로 만든다.

```python
[
    "ffmpeg", "-loglevel", "error", "-y",
    "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{width}x{height}",
    "-r", str(fps), "-i", "-", "-an", "-vf", f"scale=-2:{output_height}",
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-b:v", bitrate,
    "-movflags", "+faststart", "-f", "mp4", str(partial),
]
```

핵심 시각은 derivative-relative `max(0.0, incident-start-2.0)`, `incident-start`, `min(duration-0.001, incident-start+2.0)`이다. 가장 가까운 annotated frame을 `before.jpg`, `moment.jpg`, `after.jpg`로 `cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 88])`한 뒤 `atomic_write`로 저장한다. OpenCV capture와 FFmpeg stdin/process는 `finally`에서 닫고, non-zero FFmpeg exit나 3장 미생성은 실패시킨다.

- [ ] **Step 6: focused test와 전체 회귀 테스트를 통과시킨다**

Run: `python3 -m pytest tests/test_vision.py -q && python3 -m pytest -q`

Expected: 모든 테스트 PASS.

- [ ] **Step 7: 커밋한다**

```bash
git add src/dashpi/vision.py tests/test_vision.py
git commit -m "feat: render tracked incident overlays"
```

### Task 4: Visual Self-Contained HTML and Print/PDF Layout

**Files:**
- Modify: `src/dashpi/reports.py`
- Modify: `src/dashpi/web/index.html`
- Modify: `src/dashpi/web/receiver.html`
- Modify: `web/public/receiver.html`
- Test: `tests/test_reports.py`
- Test: `tests/test_web.py`
- Test: `web/tests/receiver.test.ts`

**Interfaces:**
- Consumes: 완성 report dict, `annotated.mp4` bytes, before/moment/after JPEG bytes
- Produces: `render_report_html(report: dict, video_bytes: bytes, keyframe_bytes: list[bytes]) -> str`

- [ ] **Step 1: self-contained/print/security 실패 테스트를 작성한다**

```python
# tests/test_reports.py
def complete_report_fixture():
    return {
        "incident_id": "inc-1",
        "triggered_at": "2026-09-06T00:00:00Z",
        "incident_timestamp": 22.5,
        "transfer_window": {"start": 17.5, "end": 27.5},
        "summary": "<script>alert(1)</script>",
        "observations": [{"timestamp": 22.5, "description": "차량 접촉"}],
        "object_observations": [{"timestamp": 22.5, "track_id": 1, "label": "car", "confidence": .91, "box": [1, 2, 30, 40]}],
        "limitations": ["단일 카메라"],
        "warnings": [],
        "overlays": {"traffic_lights": False, "lanes": False, "traffic_signs": False},
        "digests": {"clip.mp4": "abc", "annotated.mp4": "def", "before.jpg": "b", "moment.jpg": "m", "after.jpg": "a"},
        "model": "test-model",
        "generated_at": "2026-09-06T00:01:00Z",
    }

def test_html_embeds_video_three_frames_visual_stats_and_offline_controls():
    report = complete_report_fixture()
    document = render_report_html(report, b"video", [b"before", b"moment", b"after"])
    assert 'src="data:video/mp4;base64,dmlkZW8="' in document
    assert document.count('src="data:image/jpeg;base64,') == 3
    assert "Download HTML" in document and "Save as PDF" in document
    assert "object-chart" in document and "incident-timeline" in document
    assert "@media print" in document
    assert ".screen-only{display:none" in document
    assert "AI output is advisory" in document
    assert "<script>alert(1)</script>" not in document

def test_html_requires_exactly_three_keyframes():
    with pytest.raises(ValueError, match="three key frames"):
        render_report_html(complete_report_fixture(), b"video", [b"only one"])
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_reports.py::test_html_embeds_video_three_frames_visual_stats_and_offline_controls tests/test_reports.py::test_html_requires_exactly_three_keyframes -q`

Expected: FAIL because `render_report_html` still accepts only one argument.

- [ ] **Step 3: report를 한 파일의 시각적 HTML로 렌더링한다**

`render_report_html`은 모든 model 문자열을 `html.escape`하고 bytes만 `base64.b64encode`한다. 외부 URL, font, stylesheet, image, script resource는 넣지 않는다. 다음 구조와 selector를 한 문서에 포함한다.

```python
if len(keyframe_bytes) != 3:
    raise ValueError("report requires three key frames")
incident_time = float(report["incident_timestamp"])
transfer_start = float(report["transfer_window"]["start"])
transfer_end = float(report["transfer_window"]["end"])
marker_percent = min(100.0, max(0.0, (incident_time - transfer_start) / (transfer_end - transfer_start) * 100.0))
tracks: dict[str, set[int]] = {}
for item in report["object_observations"]:
    tracks.setdefault(str(item["label"]), set()).add(int(item["track_id"]))
track_count = len({track for values in tracks.values() for track in values})
largest_count = max((len(values) for values in tracks.values()), default=1)
object_chart = "".join(
    f'<div><span>{html.escape(label)}</span><i style="width:{len(values) / largest_count * 100:.2f}%"></i><b>{len(values)}</b></div>'
    for label, values in sorted(tracks.items())
) or "<p>추적된 객체 없음</p>"
object_rows = "".join(
    f'<tr><td>{float(item["timestamp"]):.2f}s</td><td>{html.escape(str(item["label"]))} #{int(item["track_id"])}</td><td>{float(item["confidence"]):.0%}</td></tr>'
    for item in report["object_observations"]
)
observation_markup = "".join(
    f'<li>{float(item["timestamp"]):.1f}s — {html.escape(str(item["description"]))}</li>'
    for item in report["observations"]
)
analysis_markup = f'<p>{html.escape(str(report["summary"]))}</p><ol>{observation_markup}</ol>'
warning_markup = "<p>AI output is advisory and may be incomplete.</p>" + "".join(
    f'<p>{html.escape(str(value))}</p>'
    for value in [*report["limitations"], *report["warnings"]]
)
digest_markup = "".join(
    f'<p><code>{html.escape(name)}</code> {html.escape(str(digest))}</p>'
    for name, digest in sorted(report["digests"].items())
)
provenance_markup = (
    f'<p>Incident: {html.escape(str(report["incident_id"]))}</p>'
    f'<p>Triggered: {html.escape(str(report["triggered_at"]))}</p>'
    f'<p>Model: {html.escape(str(report["model"]))}</p>'
    f'<p>Generated: {html.escape(str(report["generated_at"]))}</p>'
    f'<p>Optional overlays: {html.escape(json.dumps(report["overlays"], sort_keys=True))}</p>'
)
video_source = "data:video/mp4;base64," + base64.b64encode(video_bytes).decode("ascii")
frame_sources = [
    "data:image/jpeg;base64," + base64.b64encode(value).decode("ascii")
    for value in keyframe_bytes
]
cards = (
    f'<article class="card"><span>사고 시점</span><b>{incident_time:.1f}s</b></article>'
    f'<article class="card"><span>전송 구간</span><b>{transfer_start:.1f}–{transfer_end:.1f}s</b></article>'
    f'<article class="card"><span>추적 객체</span><b>{track_count}</b></article>'
)
keyframes = "".join(
    f'<figure><img src="{source}" alt="{label}"><figcaption>{label}</figcaption></figure>'
    for source, label in zip(frame_sources, ("사고 전", "사고 순간", "사고 후"), strict=True)
)
document = f'''<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DashPi 사고 분석 리포트</title><style>
:root{{color-scheme:dark;--bg:#09111f;--panel:#111d31;--line:#29405f;--text:#f5f7fb;--muted:#9fb0c7;--accent:#55a7ff;--danger:#ff5d68}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:15px/1.55 system-ui,sans-serif}}main{{max-width:1080px;margin:auto;padding:24px}}
.cards,.keyframes,.object-chart{{display:grid;gap:12px}}.cards{{grid-template-columns:repeat(3,1fr)}}.card,section{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px}}.keyframes{{grid-template-columns:repeat(3,1fr)}}img,video{{width:100%;border-radius:10px}}.incident-timeline{{position:relative;height:10px;background:#24344d;border-radius:9px}}.incident-timeline i{{position:absolute;top:-5px;width:3px;height:20px;background:var(--danger)}}.object-chart>div{{display:grid;grid-template-columns:100px 1fr 32px;align-items:center;gap:8px}}.object-chart>div i{{display:block;height:10px;background:var(--accent);border-radius:8px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:7px;border-bottom:1px solid var(--line);text-align:left}}
@media(max-width:700px){{.cards,.keyframes{{grid-template-columns:1fr}}}}
@media print{{body{{background:white;color:black}}.screen-only{{display:none!important}}section,.card{{border:1px solid #bbb;break-inside:avoid}}.keyframes{{grid-template-columns:repeat(3,1fr)}}}}
</style></head><body><main>
<header><p>DashPi · 검증된 오프라인 리포트</p><h1>사고 분석 리포트</h1></header>
<section class="screen-only"><video controls preload="metadata" src="{video_source}"></video></section>
<section class="cards">{cards}</section>
<section><h2>10초 타임라인</h2><div class="incident-timeline"><i style="left:{marker_percent:.2f}%"></i></div></section>
<section class="object-chart"><h2>객체 통계</h2>{object_chart}<table><thead><tr><th>시점</th><th>객체</th><th>신뢰도</th></tr></thead><tbody>{object_rows}</tbody></table></section>
<section class="keyframes">{keyframes}</section>
<section><h2>분석</h2>{analysis_markup}<h2>한계와 경고</h2>{warning_markup}<h2>생성 정보</h2>{provenance_markup}<h2>SHA-256</h2>{digest_markup}</section>
<nav class="screen-only"><button type="button" onclick="downloadReport()">Download HTML</button><button type="button" onclick="window.print()">Save as PDF</button></nav>
</main><script>
function downloadReport(){{const blob=new Blob(['<!doctype html>'+document.documentElement.outerHTML],{{type:'text/html'}});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='report.html';a.click();setTimeout(()=>URL.revokeObjectURL(url),0)}}
</script></body></html>'''
```

객체 그래프는 `object_observations`를 label별 unique `track_id` 수로 집계해 CSS width bar와 숫자를 서버에서 만든다. timeline marker는 `(incident_timestamp - transfer_start) / (transfer_end - transfer_start) * 100`으로 계산하고 0–100에 clamp한다. raw report JSON을 script에 삽입하지 않는다.

- [ ] **Step 4: iframe에서 검증된 report의 자체 동작만 허용한다**

`src/dashpi/web/index.html`, `src/dashpi/web/receiver.html`, `web/public/receiver.html`의 report iframe을 정확히 `sandbox="allow-scripts allow-downloads allow-modals"`로 바꾼다. `allow-same-origin`, top navigation, popups는 허용하지 않는다.

```python
# tests/test_web.py
def test_report_iframes_allow_only_offline_report_controls():
    for name in ("index.html", "receiver.html"):
        text = (WEB_ROOT / name).read_text()
        assert 'sandbox="allow-scripts allow-downloads allow-modals"' in text
        assert "allow-same-origin" not in text
```

```typescript
// web/tests/receiver.test.ts의 첫 test
assert.ok(html.includes('sandbox="allow-scripts allow-downloads allow-modals"'));
assert.equal(html.includes('allow-same-origin'), false);
```

기존 Python `render_report_html(report)` test 호출은 모두 `render_report_html(report, b"video", [b"before", b"moment", b"after"])`로 바꿔 기존 escaping assertion을 유지한다.

- [ ] **Step 5: Python과 browser source tests 및 build를 통과시킨다**

Run: `python3 -m pytest tests/test_reports.py tests/test_web.py -q && npm --prefix web test && npm --prefix web run build`

Expected: 모두 PASS, build 결과가 `src/dashpi/web`에 반영됨.

- [ ] **Step 6: 커밋한다**

```bash
git add src/dashpi/reports.py src/dashpi/web/index.html src/dashpi/web/receiver.html web/public/receiver.html web/tests/receiver.test.ts tests/test_reports.py tests/test_web.py
git commit -m "feat: build self-contained visual incident report"
```

### Task 5: Pipeline Composition, Immutable Evidence, and Tracking Fallback

**Files:**
- Modify: `src/dashpi/pipeline.py`
- Modify: `src/dashpi/cli.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: Task 1–4 interfaces, injected analyzer, optional injected detector
- Produces: `IncidentPipeline(settings: Settings, store: IncidentStore, detector=None)`, `process(incident: IncidentMetadata, segments: list[Segment], analyze, incident_offset_override: float | None = None, overlays: OverlaySettings | None = None) -> IncidentMetadata`, `generate_report(incident: IncidentMetadata, analyze, incident_offset_override: float | None = None, overlays: OverlaySettings | None = None) -> IncidentMetadata`

- [ ] **Step 1: 완성 artifact 흐름과 원본 불변 실패 테스트를 작성한다**

```python
# tests/test_pipeline.py
@pytest.fixture
def long_pipeline_fixture(tmp_path):
    source = make_video(tmp_path / "source.mp4", 46)
    segments = segment_source(source, tmp_path / "segments", 2.0)
    settings = Settings(tmp_path / "data", "test-model", pre_seconds=30.0, post_seconds=15.0)
    incident = IncidentMetadata.new(
        "inc-1", "2026-09-06T00:00:00Z", 30.0, settings.post_seconds, settings.pre_seconds
    )
    def detector(_frame):
        return [
            {"label": "car", "confidence": .91, "box": [20, 20, 90, 90]},
            {"label": "traffic light", "confidence": .82, "box": [100, 10, 125, 60]},
        ]
    pipeline = IncidentPipeline(settings, IncidentStore(settings.data_root), detector)
    return pipeline, incident, segments, detector

def localized_analysis(timestamp=3.0):
    return {
        "incident_timestamp": timestamp,
        "summary": "급정지 뒤 충돌",
        "observations": [{"timestamp": timestamp, "description": "차량 접촉"}],
        "limitations": ["단일 카메라"],
    }

def test_pipeline_creates_ten_second_annotated_report_without_mutating_evidence(long_pipeline_fixture):
    pipeline, incident, segments, detector = long_pipeline_fixture
    result = pipeline.process(incident, segments, lambda _frames: localized_analysis(22.5))
    assert result.state is IncidentState.READY
    assert result.annotated.path.name == "annotated.mp4"
    assert 9.9 <= result.annotated.duration <= 10.1
    assert result.clip.sha256 == sha256_file(result.clip.path)
    report = json.loads(result.report_json.path.read_text())
    assert report["transfer_window"] == {"start": 17.5, "end": 27.5}
    assert report["digests"]["clip.mp4"] == result.clip.sha256
    assert report["digests"]["annotated.mp4"] == result.annotated.sha256
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_pipeline.py::test_pipeline_creates_ten_second_annotated_report_without_mutating_evidence -q`

Expected: FAIL because the pipeline neither localizes nor creates `annotated.mp4`.

- [ ] **Step 3: 기존 process를 clip 단계와 report 단계로 최소 분리한다**

`IncidentPipeline.__init__(settings: Settings, store: IncidentStore, detector=None)`은 세 값을 저장한다. `process(incident: IncidentMetadata, segments: list[Segment], analyze, incident_offset_override: float | None = None, overlays: OverlaySettings | None = None) -> IncidentMetadata`는 기존 CLIPPING/build_clip/save 코드를 그대로 실행한 뒤 `generate_report(incident, analyze, incident_offset_override, overlays)`의 반환값을 그대로 반환한다. `generate_report(incident: IncidentMetadata, analyze, incident_offset_override: float | None = None, overlays: OverlaySettings | None = None) -> IncidentMetadata`는 이미 검증된 `incident.clip`만 읽고 ANALYZING 단계부터 재실행한다.

`generate_report`의 exact 순서는 다음과 같다.

1. `clip_before = sha256_file(incident.clip.path)`를 구해 metadata digest와 일치하지 않으면 즉시 `analysis_failed`.
2. `sample_frames` → injected `analyze` → `validate_report(raw, incident.clip.sha256, settings.ollama_model, generated_at, incident.clip.duration, incident_offset_override)`.
3. `transfer_window` 계산 후 `annotate_clip` 실행. detector가 `None`이면 tracker failure 경로로 보낸다.
4. `annotated.mp4`, key frame 3장, object observations, overlay dict, warning, transfer boundaries, `clip.mp4`·`annotated.mp4`·`before.jpg`·`moment.jpg`·`after.jpg` digest를 report dict에 추가한다.
5. `report.json`을 `atomic_write`하고 key frame bytes와 annotated bytes로 `report.html`을 만든다.
6. `sha256_file(clip.path) == clip_before == incident.clip.sha256`를 다시 검사한다.
7. metadata에 annotated duration/digest, localized offset, report artifacts를 넣고 `READY` 전이 후 저장한다.

- [ ] **Step 4: tracker failure fallback 실패 테스트를 작성한다**

```python
def test_tracker_failure_creates_unannotated_ten_second_report_with_warning(long_pipeline_fixture, monkeypatch):
    pipeline, incident, segments, _detector = long_pipeline_fixture
    monkeypatch.setattr("dashpi.pipeline.annotate_clip", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("tracker failed")))
    result = pipeline.process(incident, segments, lambda _frames: localized_analysis(22.5))
    assert result.state is IncidentState.READY
    assert 9.9 <= probe_duration(result.annotated.path) <= 10.1
    report = json.loads(result.report_json.path.read_text())
    assert report["object_observations"] == []
    assert "Object tracking failed; the transfer video has no boxes." in report["warnings"]
```

- [ ] **Step 5: fallback는 기존 media 함수만 조합한다**

`annotate_clip`에서 예외가 나면 `transcode_clip(clip.path, annotated.mp4, start, end-start, 480, "900k")`을 호출한다. 그 뒤 `extract_frame`으로 before/moment/after를 추출하고 object observations는 빈 list로 둔다. 이 경로의 실패만 `analysis_failed`로 전이한다. AI validation failure는 기존처럼 clip을 유지하고, 이미 완성된 annotated가 있으면 metadata에서 제거하거나 삭제하지 않는다.

CLI는 detector path가 있을 때만 `YoloDetector(settings.detector_model, settings.detection_confidence)`를 한 번 생성해 pipeline에 전달한다.

- [ ] **Step 6: focused tests와 전체 회귀 테스트를 통과시킨다**

Run: `python3 -m pytest tests/test_pipeline.py -q && python3 -m pytest -q`

Expected: 모든 테스트 PASS.

- [ ] **Step 7: 커밋한다**

```bash
git add src/dashpi/pipeline.py src/dashpi/cli.py tests/test_pipeline.py
git commit -m "feat: generate incident report artifacts"
```

### Task 6: Optical Size Fallback and Manual Transfer UI

**Files:**
- Modify: `src/dashpi/pipeline.py`
- Modify: `src/dashpi/api.py`
- Modify: `src/dashpi/web/index.html`
- Modify: `src/dashpi/web/tokens.css`
- Modify: `src/dashpi/web/sender.html`
- Modify: `web/public/sender.html`
- Test: `tests/test_pipeline.py`
- Test: `tests/test_api.py`
- Test: `tests/test_web.py`
- Test: `web/tests/sender.test.ts`

**Interfaces:**
- Consumes: 기존 `MAX_PAYLOAD`, completed 480p report, 기존 `POST /api/incidents/{id}/optical`
- Produces: one-time 360p fallback, `optical_report_available`와 `clip_duration` summary fields, explicit report regeneration request

- [ ] **Step 1: 480p → 360p → Local Wi-Fi 크기 정책 실패 테스트를 작성한다**

```python
# tests/test_pipeline.py
def recording_transcode(real, calls):
    def wrapped(source, output, start, duration, height, bitrate):
        calls.append((source, output, start, duration, height, bitrate))
        return real(source, output, start, duration, height, bitrate)
    return wrapped

def test_oversized_html_reencodes_only_derivative_once(long_pipeline_fixture, monkeypatch):
    pipeline, incident, segments, _detector = long_pipeline_fixture
    sizes = iter([MAX_PAYLOAD + 1, MAX_PAYLOAD - 1])
    monkeypatch.setattr(pipeline_module, "render_report_html", lambda *args: "x" * next(sizes))
    calls = []
    monkeypatch.setattr(
        pipeline_module,
        "transcode_clip",
        recording_transcode(pipeline_module.transcode_clip, calls),
    )
    result = pipeline.process(incident, segments, lambda _frames: localized_analysis(22.5))
    assert calls[-1][0].name == "annotated.mp4"
    assert calls[-1][4:] == (360, "450k")
    assert result.report_html.byte_length <= MAX_PAYLOAD
    assert result.clip.sha256 == sha256_file(result.clip.path)

def test_second_size_failure_keeps_ready_report_for_local_wifi(long_pipeline_fixture, monkeypatch):
    pipeline, incident, segments, _detector = long_pipeline_fixture
    monkeypatch.setattr(pipeline_module, "render_report_html", lambda *args: "x" * (MAX_PAYLOAD + 1))
    result = pipeline.process(incident, segments, lambda _frames: localized_analysis(22.5))
    report = json.loads(result.report_json.path.read_text())
    assert result.state is IncidentState.READY
    assert result.report_html.byte_length > MAX_PAYLOAD
    assert "Optical payload exceeds 16 MiB; use Local Wi-Fi." in report["warnings"]
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_pipeline.py -k 'oversized_html or second_size_failure' -q`

Expected: FAIL because no pre-packaging size fallback exists.

- [ ] **Step 3: pipeline에 정확히 한 번의 quality fallback을 추가한다**

480p HTML bytes가 `MAX_PAYLOAD`를 초과하면 `transcode_clip(annotated.path, annotated.path, 0.0, annotated.duration, 360, "450k")`로 atomic replace하고 새 digest를 report에 반영한 뒤 HTML을 다시 만든다. 두 번째 HTML도 초과하면 Local Wi-Fi warning을 report에 추가하고 `report.json`과 `report.html`을 마지막으로 다시 쓴다. `clip.mp4`는 어느 분기에서도 FFmpeg input 외에는 열지 않는다. 기존 API의 bounded verified reread와 413 응답은 유지한다.

- [ ] **Step 4: API summary와 수동 재생성 boundary 실패 테스트를 작성한다**

```python
# tests/test_api.py
def ready_store_with_clip(tmp_path, duration):
    store = IncidentStore(tmp_path)
    item = IncidentMetadata.new("inc-1", "2026-09-06T00:00:00Z", 40.0, 15.0)
    item.state = IncidentState.READY
    item.clip = replace(atomic_write(store.directory("inc-1") / "clip.mp4", b"clip"), duration=duration)
    item.report_json = atomic_write(store.directory("inc-1") / "report.json", b'{"summary":"old"}')
    item.report_html = atomic_write(store.directory("inc-1") / "report.html", b"<h1>old</h1>")
    store.save(item)
    return store, item

def test_list_reports_optical_availability_from_verified_html_size(client_with_ready_incident):
    client, _payload, _clip, _store = client_with_ready_incident
    item = client.get("/api/incidents").json()[0]
    assert item["optical_report_available"] is True
    assert item["clip_duration"] is None

def test_report_regeneration_passes_manual_time_and_overlay_settings(tmp_path):
    store, item = ready_store_with_clip(tmp_path, duration=45.0)
    calls = []
    def regenerate(incident, offset, overlays):
        calls.append((incident.incident_id, offset, overlays))
        return incident
    client = TestClient(create_app(store, regenerate_report=regenerate))
    assert client.get("/api/incidents").json()[0]["clip_duration"] == 45.0
    response = client.post("/api/incidents/inc-1/report", json={
        "incident_offset_seconds": 4.0,
        "traffic_lights": True,
        "lanes": False,
        "traffic_signs": True,
    })
    assert response.status_code == 200
    assert calls == [("inc-1", 4.0, OverlaySettings(True, False, True))]

def test_report_regeneration_rejects_time_outside_evidence(tmp_path):
    store, _item = ready_store_with_clip(tmp_path, duration=45.0)
    client = TestClient(create_app(store, regenerate_report=lambda *_: pytest.fail()))
    assert client.post("/api/incidents/inc-1/report", json={"incident_offset_seconds": 46.0}).status_code == 422
```

`create_app`의 새 optional argument는 `regenerate_report: Callable[[IncidentMetadata, float | None, OverlaySettings], IncidentMetadata] | None = None`이다. callback이 없으면 endpoint는 503을 반환한다. 요청 Pydantic model의 세 bool 기본값은 false이고 offset은 optional `ge=0`; clip duration보다 큰 값은 callback 전에 422로 거절한다. metadata를 store의 descriptor-safe load로 읽고 incident ID가 route와 같은지 확인한다.

```python
class ReportBuildRequest(BaseModel):
    incident_offset_seconds: float | None = Field(default=None, ge=0)
    traffic_lights: bool = False
    lanes: bool = False
    traffic_signs: bool = False

    def overlays(self) -> OverlaySettings:
        return OverlaySettings(self.traffic_lights, self.lanes, self.traffic_signs)
```

- [ ] **Step 5: 로컬 화면에 설정과 명시적 전송 진입을 추가한다**

`GET /api/incidents`는 `clip_duration: item.clip.duration if item.clip else None`과 `optical_report_available: item.state is READY and item.report_html is not None and item.report_html.byte_length <= MAX_PAYLOAD`를 반환한다. 선택 incident 아래에 세 checkbox, 0–`clip_duration` 숫자 입력, `리포트 다시 만들기`, `정차 후 휴대폰으로 보내기` 링크를 둔다. 재생성 POST body는 위 API shape 그대로 사용한다. offset을 비워 두면 AI가 다시 찾고 값이 있으면 수동 offset을 사용한다. `optical_report_available == false`이면 sender 링크를 숨기고 `16 MiB를 초과해 Local Wi-Fi에서 HTML을 다운로드하세요.`를 표시한다.

sender의 기존 privacy checkbox 문구는 다음으로 바꾼다.

```html
<label class="acknowledgement">
  <input id="warning" type="checkbox" aria-describedby="warning-copy">
  안전한 장소에 정차했고, 주변에서 화면을 볼 수 있는 사람이 없는지 확인했습니다.
</label>
```

기존 `web/src/sender.ts`는 수정하지 않는다. start button click 안에서만 optical POST를 호출하는지, report가 기본 option인지, 정차 checkbox 전에는 disabled인지 기존 test에 한국어 문구 assertion을 추가한다.

```typescript
// web/tests/sender.test.ts의 첫 test
assert.ok(html.includes('안전한 장소에 정차했고'));
assert.ok(html.indexOf('<option value="report">') < html.indexOf('<option value="clip">'));
assert.ok(html.includes('<button id="start" type="button" disabled>'));
```

- [ ] **Step 6: API/UI/browser tests와 build를 통과시킨다**

Run: `python3 -m pytest tests/test_pipeline.py tests/test_api.py tests/test_web.py -q && npm --prefix web test && npm --prefix web run build`

Expected: 모두 PASS. 기존 oversized payload 413, descriptor verification, SHA-256 tests도 그대로 PASS.

- [ ] **Step 7: 커밋한다**

```bash
git add src/dashpi/pipeline.py src/dashpi/api.py src/dashpi/web/index.html src/dashpi/web/tokens.css src/dashpi/web/sender.html web/public/sender.html web/tests/sender.test.ts tests/test_pipeline.py tests/test_api.py tests/test_web.py
git commit -m "feat: enforce optical report size policy"
```

### Task 7: Recording-Priority Analysis Worker and Retry Wiring

**Files:**
- Create: `src/dashpi/analysis_worker.py`
- Modify: `src/dashpi/pipeline.py`
- Modify: `src/dashpi/api.py`
- Modify: `src/dashpi/server.py`
- Test: `tests/test_analysis_worker.py`
- Test: `tests/test_pipeline.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `IncidentPipeline.generate_report`, production Ollama client/detector, recorder pressure signal
- Produces: `AnalysisWorker.submit(work: Callable[[], T]) -> Future[T]`, `pause() -> None`, `resume() -> None`, `wait_for_capacity() -> None`

- [ ] **Step 1: 단일 background worker와 cooperative pause 실패 테스트를 작성한다**

```python
# tests/test_analysis_worker.py
from threading import Event
from dashpi.analysis_worker import AnalysisWorker

def test_analysis_waits_during_recording_pressure_without_blocking_caller():
    worker = AnalysisWorker()
    ran = Event()
    worker.pause()
    future = worker.submit(lambda: (worker.wait_for_capacity(), ran.set()))
    assert future.done() is False
    assert ran.is_set() is False
    worker.resume()
    future.result(timeout=2)
    assert ran.is_set()
    worker.close()

def test_worker_runs_only_one_analysis_at_a_time():
    worker = AnalysisWorker()
    first_release, second_started = Event(), Event()
    first = worker.submit(lambda: first_release.wait(2))
    second = worker.submit(second_started.set)
    assert not second_started.wait(.1)
    first_release.set(); first.result(timeout=2); second.result(timeout=2)
    worker.close()
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/test_analysis_worker.py -q`

Expected: FAIL with `ModuleNotFoundError: dashpi.analysis_worker`.

- [ ] **Step 3: 표준 라이브러리 worker만 구현한다**

```python
# src/dashpi/analysis_worker.py
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

class AnalysisWorker:
    def __init__(self):
        self._capacity = Event()
        self._capacity.set()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dashpi-analysis")

    def pause(self) -> None:
        self._capacity.clear()

    def resume(self) -> None:
        self._capacity.set()

    def wait_for_capacity(self) -> None:
        self._capacity.wait()

    def submit(self, work: Callable[[], T]) -> Future[T]:
        return self._executor.submit(work)

    def close(self) -> None:
        self._capacity.set()
        self._executor.shutdown(wait=True, cancel_futures=True)
```

- [ ] **Step 4: pipeline의 무거운 단계 사이에 pause point를 넣는다**

`IncidentPipeline.__init__`은 `wait_for_capacity: Callable[[], None] = lambda: None`을 받는다. `sample_frames` 전, Ollama `analyze` 전, `annotate_clip` 또는 fallback transcode 전, HTML quality transcode 전에 각각 한 번 호출한다. frame별 pause나 새 scheduler, process pool, queue package는 추가하지 않는다.

```python
def test_pipeline_checks_recording_capacity_before_expensive_stages(long_pipeline_fixture):
    calls = []
    pipeline, incident, segments, detector = long_pipeline_fixture
    pipeline.wait_for_capacity = lambda: calls.append("capacity")
    pipeline.process(incident, segments, lambda _frames: localized_analysis(22.5))
    assert len(calls) >= 3
```

- [ ] **Step 5: server의 재생성 endpoint를 worker에 연결한다**

`server.py`에 optional `--ollama-model`, `--detector-model`, 세 overlay flag를 추가한다. Ollama model과 detector가 모두 설정됐을 때 `AnalysisWorker()`와 `IncidentPipeline(settings, store, detector, wait_for_capacity=worker.wait_for_capacity)`를 한 번 만든다. API callback은 `worker.submit(lambda: pipeline.generate_report(item, client.analyze, offset, overlays))`를 반환한다. API는 Future를 받으면 `202 {"state":"analyzing"}`를 반환하고 즉시 요청 thread를 놓는다. 설정이 없으면 조회/다운로드/기존 optical 기능은 유지되고 재생성만 503이다.

Task 6의 `regenerate_report` 반환 type을 `IncidentMetadata | Future[IncidentMetadata]`로 넓히고 endpoint에서 다음 분기만 추가한다.

```python
result = regenerate_report(item, request.incident_offset_seconds, request.overlays())
if isinstance(result, Future):
    return JSONResponse({"state": "analyzing"}, status_code=202)
return {"state": result.state}
```

FastAPI shutdown event에서 `worker.close()`를 호출한다. recorder 구현은 CPU·memory·thermal 압력이 높을 때 같은 worker의 `pause()`, 회복 시 `resume()`만 호출하면 되며 분석 단계 내부를 침범하지 않는다.

- [ ] **Step 6: 분석 대기 중 새 recording segment를 만들 수 있는 통합 테스트를 추가한다**

```python
# tests/test_analysis_worker.py
def test_recording_continues_while_analysis_is_paused(tmp_path):
    worker = AnalysisWorker(); worker.pause()
    future = worker.submit(lambda: (worker.wait_for_capacity(), "analyzed")[1])
    segment = make_video(tmp_path / "new-segment.mp4", 2)
    assert segment.exists() and not future.done()
    worker.resume()
    assert future.result(timeout=2) == "analyzed"
    worker.close()
```

- [ ] **Step 7: focused tests와 전체 회귀 테스트를 통과시킨다**

Run: `python3 -m pytest tests/test_analysis_worker.py tests/test_pipeline.py tests/test_server.py tests/test_api.py -q && python3 -m pytest -q`

Expected: 모든 테스트 PASS.

- [ ] **Step 8: 커밋한다**

```bash
git add src/dashpi/analysis_worker.py src/dashpi/pipeline.py src/dashpi/api.py src/dashpi/server.py tests/test_analysis_worker.py tests/test_pipeline.py tests/test_server.py tests/test_api.py
git commit -m "feat: keep incident analysis behind recording"
```

### Task 8: Offline End-to-End Report and Existing Optical Regression

**Files:**
- Modify: `tests/test_offline_e2e.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: complete incident pipeline, self-contained report bytes, existing `OpticalSession`, `FountainDecoder`, `unpack_container`
- Produces: one deterministic offline proof from 45-second evidence to verified `report.html`

- [ ] **Step 1: 전체 offline flow 실패 테스트를 작성한다**

```python
# tests/test_offline_e2e.py
def test_incident_report_survives_existing_optical_transport_offline(tmp_path, monkeypatch):
    monkeypatch.setattr(socket, "create_connection", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("outbound network attempted")))
    pipeline, incident, segments = deterministic_45_second_pipeline(tmp_path)
    result = pipeline.process(incident, segments, deterministic_analysis)
    payload = result.report_html.path.read_bytes()
    assert len(payload) <= MAX_PAYLOAD

    session = OpticalSession.from_bytes("report.html", payload, "text/html", 1024, 11)
    wires = [
        session.frame(n) for n in range(session.encoder.block_count * 2)
        if n % 20 not in {1, 7, 13}
    ]
    wires += wires[:20]
    random.Random(5).shuffle(wires)
    first = parse_frame(wires[0])
    decoder = FountainDecoder(first.block_count, first.block_size, first.total_length)
    for wire in wires:
        frame = parse_frame(wire)
        decoder.add(frame.indices, frame.symbol)
        if decoder.result() is not None:
            break
    packed = decoder.result()
    assert packed is not None
    recovered = unpack_container(packed)
    assert recovered.name == "report.html"
    assert recovered.sha256 == hashlib.sha256(payload).hexdigest()
    assert b"data:video/mp4;base64," in recovered.payload
    assert recovered.payload.count(b"data:image/jpeg;base64,") == 3
```

별도 optical protocol fixture나 Decimen 자료를 만들지 않는다.

- [ ] **Step 2: 새 E2E가 기존 fixture helper 부재로 실패하는지 확인한다**

Run: `python3 -m pytest tests/test_offline_e2e.py::test_incident_report_survives_existing_optical_transport_offline -q`

Expected: FAIL because the deterministic full-report helper does not exist yet.

- [ ] **Step 3: test-local helper만 추가하고 production optical 코드는 수정하지 않는다**

```python
# tests/test_offline_e2e.py
def deterministic_analysis(_frames):
    return {
        "incident_timestamp": 22.5,
        "summary": "급정지 뒤 접촉",
        "observations": [{"timestamp": 22.5, "description": "차량 접촉"}],
        "limitations": ["단일 전방 카메라"],
    }

def deterministic_45_second_pipeline(tmp_path):
    source = make_video(tmp_path / "source.mp4", 46)
    segments = segment_source(source, tmp_path / "segments", 2.0)
    settings = Settings(tmp_path / "data", "test-model", pre_seconds=30.0, post_seconds=15.0)
    incident = IncidentMetadata.new(
        "inc-e2e", "2026-09-06T00:00:00Z", 30.0, settings.post_seconds, settings.pre_seconds
    )
    def detector(_frame):
        return [{"label": "car", "confidence": .91, "box": [20, 20, 90, 90]}]
    return IncidentPipeline(settings, IncidentStore(settings.data_root), detector), incident, segments
```

optical frame loss는 기존과 동일한 15%, duplicate 20개, deterministic reorder seed 5를 사용한다. `src/dashpi/optical/container.py`, `fountain.py`, `protocol.py`, `session.py`에는 diff가 없어야 한다.

- [ ] **Step 4: README의 결과물과 실행 명령을 현재 계약으로 갱신한다**

README storage layout에 `annotated.mp4`를 추가하고 다음 내용을 명시한다.

- 원본 `clip.mp4`는 30초 전 + 15초 후이며 오버레이하지 않는다.
- `report.html`은 10초 annotated video와 핵심 장면 3장을 포함한다.
- 선택 overlay CLI flags와 기본 OFF.
- 광학 전송 전 정차, 16 MiB 초과 시 Local Wi-Fi 사용.
- Download HTML과 browser Save as PDF의 차이.
- detector는 YOLOv8 COCO ONNX `[1,84,8400]` 또는 `[1,8400,84]` 형식이다.

- [ ] **Step 5: Python, browser, package 전체 검증을 실행한다**

Run: `python3 -m pytest -q && npm --prefix web test && npm --prefix web run build && git diff --check`

Expected: Python/TypeScript test 모두 PASS, build 성공, whitespace error 없음.

- [ ] **Step 6: 광학 wire format 불변을 확인한다**

Run: `git diff 3a2e791 -- src/dashpi/optical tests/fixtures/optical-v1.json tests/fixtures/optical-e2e.json`

Expected: empty output.

- [ ] **Step 7: 최종 커밋한다**

```bash
git add README.md tests/test_offline_e2e.py
git commit -m "test: verify offline incident report delivery"
```

## Execution Notes

- Task 1–7은 각자 실패 테스트 → 실패 확인 → 최소 구현 → 통과 확인 → 커밋 순서를 바꾸지 않는다.
- Task 3의 detector는 한 가지 YOLOv8 COCO ONNX 형식만 지원한다. 다른 model family가 실제 설치 요건이 될 때 그때 adapter를 추가한다.
- Task 7은 한 번에 하나의 분석만 허용한다. Raspberry Pi 측정에서 backlog가 실제 문제가 될 때만 queue 정책을 확장한다.
- Hardware acceptance 전까지 성능 수치는 추정해 문서에 넣지 않는다.

## Post-Implementation Raspberry Pi Acceptance

Desktop 구현과 커밋이 끝난 뒤 실제 Raspberry Pi에서 30분 연속 녹화 중 report 3건을 생성한다. 각 실행마다 누락 segment 수(기대 0), inference 초, annotated encode 초, peak RSS MiB, peak CPU %, peak 온도 °C, optical 전송 초, 휴대폰 decode 성공 여부를 기록한다. 누락 segment가 하나라도 있으면 release하지 않고 recorder가 worker `pause()`를 더 일찍 호출하도록 device pressure threshold를 조정한 뒤 같은 30분 시험을 반복한다.
