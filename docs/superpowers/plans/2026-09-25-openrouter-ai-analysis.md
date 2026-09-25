# OpenRouter 사고 분석 전환 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pi의 로컬 Ollama 분석을 OpenRouter(OpenAI 호환 API)의 3역할 분석(시점 탐지·장면 관찰·요약)으로 바꾸고, 인터넷이 없을 때는 "분석 대기" 후 자동 재시도하며, 비용 한도와 평가 하네스를 갖춘다.

**Architecture:** `ai_client.py`가 HTTP·오류 분류·설정 파일을 맡고, `analysis.py`가 역할별 프롬프트/스키마와 `Analyzer`를 제공한다. 파이프라인은 분석 함수의 인자만 넓히고(`frames, clip_path, frame_dir, override`), 재시도 가능한 오류를 새 상태 `awaiting_analysis`로 저장한다. `analysis_retry.py`가 대기 사고를 1분 주기로 재분석하고, Pi 앱·CLI·웹 서버가 같은 `build_analyzer()`를 쓴다.

**Tech Stack:** Python 3.11+ 표준 라이브러리(`urllib`, `json`, `http.server` 테스트), ffmpeg, PySide6(Pi 앱), pytest.

**Spec:** `docs/superpowers/specs/2026-09-25-openrouter-ai-analysis-design.md`

## Global Constraints

- 새 Python 의존성을 추가하지 않는다 (`pyproject.toml`의 dependencies 불변).
- 기본 base URL: `https://openrouter.ai/api/v1`, 엔드포인트 `POST {base_url}/chat/completions`.
- 기본 모델: 비전(A·B) `x-ai/grok-4.7`, 요약(C) `x-ai/grok-4.20`. 모델 이름 `fake`는 네트워크 없는 가짜 분석기.
- 키 파일: `~/.config/dashpi/ai.env` (`KEY=VALUE`), 키: `DASHPI_AI_API_KEY`, `DASHPI_AI_BASE_URL`, `DASHPI_AI_DAILY_LIMIT`(기본 20). 같은 이름의 환경 변수가 파일보다 우선.
- 요청 본문에 항상 `response_format`(json_schema, `strict: true`), `max_tokens`, `reasoning: {"effort": "low"}`, `provider: {"data_collection": "deny"}`.
- `max_tokens`: 시점 탐지 300, 장면 관찰 1500, 요약 1200. 프레임은 역할당 12장, 긴 변 1024px.
- 장면 관찰 구간: 사고 시각 ±3초(클립 경계 안).
- 재시도 간격: 1분 → 2분 → 5분 → 10분 → 이후 30분. 하루 한도 초과 시 다음 날 00:05(기기 현지 시각).
- 재시도(분석 대기): 연결 실패·DNS·시간 초과, HTTP 408/429/5xx, API 키 없음, 하루 한도. 실패(분석 실패): HTTP 400/401/402/403/404 등 나머지 4xx, 거부, `finish_reason: "length"`, 응답 JSON 이상, 리포트 검증 실패.
- 표시 문구: 상태 `awaiting_analysis` = "분석 대기". API 키 값과 이미지 내용은 로그에 쓰지 않는다.
- 모든 자동 테스트는 외부 네트워크를 호출하지 않는다.
- 랜딩·README에 제공사 이름(OpenRouter, OpenAI, xAI, Grok)을 쓰지 않는다.
- 테스트 실행: `PYTHONPATH=src QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`

## Review Focus

1. **키 파일이 아예 없는 새 Pi** — 앱은 정상 시작하고, 사고는 "분석 대기 · API 키 없음"이 되며 설정 화면은 "API 키: 없음"을 보인다 (Task 4, Task 10 테스트).
2. **사람이 손으로 만든 `ai.env`** — CRLF 줄바꿈, 따옴표로 감싼 값, 공백, `#` 주석, `export ` 접두어가 있어도 읽힌다 (Task 4 테스트).
3. **구조화 출력을 무시하는 제공사** — `content`가 ```` ```json ```` 코드 펜스로 감싸져 오거나 HTTP 200 본문에 `error` 객체가 오는 경우 올바르게 분류한다 (Task 4 테스트).
4. **클립 끝·아주 짧은 클립의 사고 시각** — 관찰 구간이 음수·클립 밖이 되지 않고, 1초 미만 구간이면 클립 전체를 쓴다 (Task 6 테스트).
5. **이전 버전 메타데이터·손상된 사용량 파일** — `analysis_attempts`/`next_analysis_at`이 없는 기존 사고와 JSON이 깨진 `ai-usage.json`이 앱을 멈추지 않는다 (Task 2, Task 5, Task 8 테스트).

---

## File Structure

| 파일 | 역할 |
| --- | --- |
| `src/dashpi/ai_client.py` (신규) | `ChatClient`, `AnalysisError`, `RetryableAnalysisError`, `AIConfig`, `load_ai_config`, `retry_delay` |
| `src/dashpi/ai_budget.py` (신규) | `DailyBudget` — 하루 분석 건수 제한 |
| `src/dashpi/analysis.py` (신규) | 역할 A·B·C 프롬프트/스키마, `locate`/`observe`/`summarize`, `Analyzer`, `FakeAnalyzer`, `build_analyzer`, `api_key_configured` |
| `src/dashpi/analysis_retry.py` (신규) | `AnalysisRetrier` — 분석 대기 사고 재시도 |
| `src/dashpi/evaluation.py` (신규) | 하네스 사례 로드, 채점, 비용 계산, 실행 |
| `src/dashpi/config.py` | `Settings.ai_model`, `ai_report_model`, `report_model_label` |
| `src/dashpi/device.py` | `VideoSettings.ai_model`, `ai_report_model`, 구 키 무시 |
| `src/dashpi/models.py` | `AWAITING_ANALYSIS`, `analysis_attempts`, `next_analysis_at` |
| `src/dashpi/storage.py` | 새 필드 기본값 |
| `src/dashpi/api.py` | 분석 대기 사고도 클립 제공 |
| `src/dashpi/media.py` | `sample_frames` 구간·축소 |
| `src/dashpi/pipeline.py` | 새 분석 인자, 대기 전이, `analysis` 보존 |
| `src/dashpi/reports.py` | `OllamaClient` 제거 |
| `src/dashpi/desktop.py` | 분석기 연결, 재시도 타이머, 설정 두 모델·키 상태, 대기 표시, 다시 분석 |
| `src/dashpi/cli.py` | `--ai-model`/`--ai-report-model`, `eval` 하위 명령 |
| `src/dashpi/server.py` | `--ai-model`/`--ai-report-model`, `build_analyzer` |
| `ai.env.example`, `.gitignore`, `README.md`, `docs/AGENT_HANDOFF.md`, `eval/README.md` | 문서·예시 |

---

### Task 1: 모델 설정 이름 바꾸기 (`ollama_model` → `ai_model` + `ai_report_model`)

**Files:**
- Modify: `src/dashpi/config.py`, `src/dashpi/device.py`, `src/dashpi/pipeline.py:122,229`, `src/dashpi/desktop.py`, `src/dashpi/cli.py`, `src/dashpi/server.py`
- Test: `tests/test_config.py`, `tests/test_device.py`, 그리고 `ollama_model`을 쓰는 모든 테스트

**Interfaces:**
- Produces: `Settings(data_root, ai_model, ai_report_model="x-ai/grok-4.20", ...)`, `Settings.report_model_label -> str`; `VideoSettings.ai_model="x-ai/grok-4.7"`, `VideoSettings.ai_report_model="x-ai/grok-4.20"`. 이 태스크에서는 `OllamaClient(settings.ai_model)`을 그대로 쓴다(Task 9에서 제거).

- [ ] **Step 1: Write the failing tests**

`tests/test_config.py`의 두 테스트를 바꾼다:

```python
def test_settings_use_approved_defaults(tmp_path: Path):
    settings = Settings(data_root=tmp_path, ai_model="x-ai/grok-4.7")
    assert (settings.segment_seconds, settings.pre_seconds, settings.post_seconds) == (2.0, 30.0, 15.0)
    assert settings.frame_sample_count == 12
    assert settings.ai_report_model == "x-ai/grok-4.20"
    assert settings.report_model_label == "x-ai/grok-4.7 + x-ai/grok-4.20"


def test_model_names_are_required(tmp_path: Path):
    with pytest.raises(ValueError, match="ai_model"):
        Settings(data_root=tmp_path, ai_model="")
    with pytest.raises(ValueError, match="ai_report_model"):
        Settings(data_root=tmp_path, ai_model="m", ai_report_model=" ")


def test_fake_model_label_is_plain(tmp_path: Path):
    assert Settings(tmp_path, "fake").report_model_label == "fake"
```

`tests/test_device.py`에 추가하고 기존 `ollama_model="qwen2.5vl:3b"` 인자를 `ai_model="x-ai/grok-4.7"`로 바꾼다:

```python
def test_old_settings_file_with_ollama_model_loads_new_defaults(tmp_path):
    import json
    from dashpi.device import load_settings

    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"width": 1280, "height": 720, "fps": 24, "bitrate_mbps": 8,
                                "brightness": 0.0, "ollama_model": "gemma3:4b"}))
    loaded = load_settings(path)

    assert (loaded.width, loaded.ai_model, loaded.ai_report_model) == (1280, "x-ai/grok-4.7", "x-ai/grok-4.20")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_config.py tests/test_device.py -k "defaults or required or fake_model or ollama_model"`
Expected: FAIL (`unexpected keyword argument 'ai_model'`)

- [ ] **Step 3: Implement**

`src/dashpi/config.py`의 `Settings`:

```python
@dataclass(frozen=True)
class Settings:
    data_root: Path
    ai_model: str
    ai_report_model: str = "x-ai/grok-4.20"
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
        if not self.ai_model.strip():
            raise ValueError("ai_model is required")
        if not self.ai_report_model.strip():
            raise ValueError("ai_report_model is required")
        if min(self.segment_seconds, self.pre_seconds, self.post_seconds) <= 0:
            raise ValueError("recording durations must be positive")
        if not 0.0 < self.detection_confidence <= 1.0:
            raise ValueError("detection_confidence must be in (0, 1]")

    @property
    def report_model_label(self) -> str:
        return "fake" if self.ai_model == "fake" else f"{self.ai_model} + {self.ai_report_model}"
```

`src/dashpi/device.py`의 `VideoSettings`와 `load_settings`:

```python
    brightness: float = 0.0
    ai_model: str = "x-ai/grok-4.7"
    ai_report_model: str = "x-ai/grok-4.20"

    def __post_init__(self) -> None:
        ...  # 기존 해상도·fps·bitrate·brightness 검사 유지
        for name in ("ai_model", "ai_report_model"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError("AI model is required")


def load_settings(path: Path) -> VideoSettings:
    if not path.exists():
        return VideoSettings()
    raw = json.loads(path.read_text())
    if type(raw) is not dict:
        raise ValueError("invalid device settings")
    raw.pop("ollama_model", None)  # pre-OpenRouter settings: fall back to the new default models
    return VideoSettings(**raw)
```

`src/dashpi/pipeline.py`: `self.settings.ollama_model`(두 곳, validate_report 인자와 `incident.report_model`)을 `self.settings.report_model_label`로 바꾼다.

`src/dashpi/desktop.py`:
- `_begin`의 `replace(self.session.settings, ollama_model=...)` → `replace(self.session.settings, ai_model=self.session.recorder.settings.ai_model, ai_report_model=self.session.recorder.settings.ai_report_model)`, `OllamaClient(self.session.settings.ollama_model)` → `OllamaClient(self.session.settings.ai_model)`.
- `_build_settings`: `QLineEdit(current.ollama_model)` → `QLineEdit(current.ai_model)`.
- `_save_settings`: `ollama_model=self.model.text().strip()` → `ai_model=self.model.text().strip()`.
- `_analyze_external`: `load_settings(...).ollama_model` → `.ai_model`, `replace(..., ollama_model=model)` → `replace(..., ai_model=model)`.
- `main()`: `Settings(root, current.ollama_model)` → `Settings(root, current.ai_model, current.ai_report_model)`, `OllamaClient(settings.ollama_model)` → `OllamaClient(settings.ai_model)`.

`src/dashpi/cli.py`: `--ollama-model` 인자를 `--ai-model`(default `"x-ai/grok-4.7"`)로, `Settings(args.data_root, args.ollama_model, ...)` → `Settings(args.data_root, args.ai_model, ...)`, `OllamaClient(settings.ollama_model)` → `OllamaClient(settings.ai_model)`.

`src/dashpi/server.py`: `--ollama-model` → `--ai-model`, `args.ollama_model` → `args.ai_model`(두 곳), `OllamaClient(settings.ollama_model)` → `OllamaClient(settings.ai_model)`.

테스트 전체에서 이름을 바꾼다:

```bash
grep -rl "ollama_model\|ollama-model" tests | xargs sed -i '' -e 's/ollama_model=/ai_model=/g' -e 's/--ollama-model/--ai-model/g' -e 's/args.ollama_model/args.ai_model/g'
grep -rn "ollama" tests src   # 남은 곳은 OllamaClient 사용처뿐이어야 한다(Task 9에서 제거)
```

`tests/test_server.py`의 `assert args.ollama_model == "vision"` → `assert args.ai_model == "vision"`.

- [ ] **Step 4: Run all tests**

Run: `PYTHONPATH=src QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: 모두 PASS

- [ ] **Step 5: Commit**

```bash
git add -A src tests
git commit -m "refactor: rename analysis model settings to ai_model and ai_report_model"
```

---

### Task 2: "분석 대기" 상태와 재시도 필드

**Files:**
- Modify: `src/dashpi/models.py`, `src/dashpi/storage.py:76-95`, `src/dashpi/api.py:94,224,259`, `src/dashpi/desktop.py` (`STATE_LABELS`)
- Test: `tests/test_models.py`(없으면 생성), `tests/test_api.py`, `tests/test_desktop.py`

**Interfaces:**
- Produces: `IncidentState.AWAITING_ANALYSIS == "awaiting_analysis"`; `IncidentMetadata.analysis_attempts: int = 0`, `IncidentMetadata.next_analysis_at: str | None = None`.

- [ ] **Step 1: Write the failing tests**

`tests/test_models.py`:

```python
import json

from dashpi.models import IncidentMetadata, IncidentState
from dashpi.storage import IncidentStore


def test_awaiting_analysis_round_trips_with_retry_fields(tmp_path):
    store = IncidentStore(tmp_path)
    item = IncidentMetadata.new("inc-1", "2026-09-25T00:00:00+00:00", 10.0, 15.0)
    item.analysis_attempts = 2
    item.next_analysis_at = "2026-09-25T00:05:00+00:00"
    item.transition(IncidentState.AWAITING_ANALYSIS, "2026-09-25T00:03:00+00:00", "인터넷 연결 없음")
    store.save(item)

    loaded = store.load("inc-1")
    assert loaded.state is IncidentState.AWAITING_ANALYSIS
    assert (loaded.analysis_attempts, loaded.next_analysis_at) == (2, "2026-09-25T00:05:00+00:00")
    assert loaded.failure_reason == "인터넷 연결 없음"


def test_metadata_written_before_retry_fields_still_loads(tmp_path):
    store = IncidentStore(tmp_path)
    item = IncidentMetadata.new("old", "2026-09-24T00:00:00+00:00", 10.0, 15.0)
    store.save(item)
    path = store.directory("old") / "metadata.json"
    raw = json.loads(path.read_text())
    del raw["analysis_attempts"], raw["next_analysis_at"]
    path.write_text(json.dumps(raw))

    loaded = store.load("old")
    assert (loaded.analysis_attempts, loaded.next_analysis_at) == (0, None)
```

`tests/test_api.py`에 추가(파일의 `ready_store_with_clip` 도우미를 사용):

```python
def test_clip_is_served_while_analysis_is_awaiting(tmp_path):
    from fastapi.testclient import TestClient
    from dashpi.api import create_app
    from dashpi.models import IncidentState

    store, item = ready_store_with_clip(tmp_path, 6.0)
    item.transition(IncidentState.AWAITING_ANALYSIS, "2026-09-25T00:00:00+00:00", "인터넷 연결 없음")
    store.save(item)

    response = TestClient(create_app(store)).get(f"/api/incidents/{item.incident_id}/clip")
    assert response.status_code in (200, 206)
```

`tests/test_desktop.py`에 추가:

```python
def test_awaiting_analysis_has_a_korean_label():
    from dashpi.desktop import STATE_LABELS
    from dashpi.models import IncidentState

    assert STATE_LABELS[IncidentState.AWAITING_ANALYSIS] == "분석 대기"
```

(기존 `test_record_labels_read_as_local_date_and_korean_state`의 `set(STATE_LABELS) == set(IncidentState)`도 이 라벨이 있어야 통과한다.)

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=src QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_models.py tests/test_api.py tests/test_desktop.py -k "awaiting or retry_fields or korean_state"`
Expected: FAIL (`AWAITING_ANALYSIS` 없음)

- [ ] **Step 3: Implement**

`src/dashpi/models.py`:

```python
class IncidentState(StrEnum):
    COLLECTING_POST_TRIGGER = "collecting_post_trigger"
    CLIPPING = "clipping"
    ANALYZING = "analyzing"
    AWAITING_ANALYSIS = "awaiting_analysis"
    READY = "ready"
    CLIP_FAILED = "clip_failed"
    ANALYSIS_FAILED = "analysis_failed"
```

`IncidentMetadata`의 마지막 필드 뒤에 추가:

```python
    incident_offset_seconds: float | None = None
    analysis_attempts: int = 0
    next_analysis_at: str | None = None
```

`src/dashpi/storage.py`의 `_metadata_from_raw`에서 `raw.setdefault("incident_offset_seconds", None)` 아래에:

```python
            raw.setdefault("analysis_attempts", 0)
            raw.setdefault("next_analysis_at", None)
```

`src/dashpi/api.py`의 세 집합 `{IncidentState.READY, IncidentState.ANALYSIS_FAILED}`(94·224·259행 부근)을 모두 `{IncidentState.READY, IncidentState.ANALYSIS_FAILED, IncidentState.AWAITING_ANALYSIS}`로 바꾼다. 파일 상단에 상수로 두고 재사용한다:

```python
CLIP_AVAILABLE = {IncidentState.READY, IncidentState.ANALYSIS_FAILED, IncidentState.AWAITING_ANALYSIS}
```

`src/dashpi/desktop.py`의 `STATE_LABELS`에 `IncidentState.AWAITING_ANALYSIS: "분석 대기",` 추가.

- [ ] **Step 4: Run all tests**

Run: `PYTHONPATH=src QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dashpi/models.py src/dashpi/storage.py src/dashpi/api.py src/dashpi/desktop.py tests
git commit -m "feat: add awaiting_analysis incident state with retry fields"
```

---

### Task 3: 프레임 추출 구간과 축소

**Files:**
- Modify: `src/dashpi/media.py:205-229`
- Test: `tests/test_media.py`

**Interfaces:**
- Produces: `sample_frames(clip: Path, output_dir: Path, count: int, start: float = 0.0, end: float | None = None, max_edge: int = 1024) -> list[tuple[Path, float]]` — 반환 시각은 **클립 기준 절대 시각**.

- [ ] **Step 1: Write the failing tests**

```python
def test_sample_frames_covers_a_window_and_limits_the_long_edge(tmp_path):
    import cv2
    from dashpi.media import sample_frames
    from tests.media_factory import make_video

    clip = make_video(tmp_path / "clip.mp4", 6)  # make_video 크기가 1024보다 작으면 max_edge=64로 축소를 검증
    frames = sample_frames(clip, tmp_path / "window", 4, start=2.0, end=4.0, max_edge=64)

    assert [round(timestamp, 2) for _path, timestamp in frames] == [2.25, 2.75, 3.25, 3.75]
    height, width = cv2.imread(str(frames[0][0])).shape[:2]
    assert max(height, width) == 64


def test_sample_frames_never_upscales(tmp_path):
    import cv2
    from dashpi.media import sample_frames
    from tests.media_factory import make_video

    clip = make_video(tmp_path / "clip.mp4", 2)
    original = cv2.imread(str(sample_frames(clip, tmp_path / "a", 1, max_edge=100000)[0][0])).shape[:2]
    assert max(original) < 100000
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_media.py -k "window or upscales"`
Expected: FAIL (`unexpected keyword argument 'start'`)

- [ ] **Step 3: Implement**

```python
def sample_frames(
    clip: Path,
    output_dir: Path,
    count: int,
    start: float = 0.0,
    end: float | None = None,
    max_edge: int = 1024,
) -> list[tuple[Path, float]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stop = probe_duration(clip) if end is None else end
    span = max(0.0, stop - start)
    # Fit inside max_edge x max_edge, keep aspect, never upscale, even dimensions for JPEG encoders.
    scale = (
        f"scale='min({max_edge},iw)':'min({max_edge},ih)':force_original_aspect_ratio=decrease:"
        "force_divisible_by=2"
    )
    paths = []
    for index in range(count):
        target = output_dir / f"{index:02d}.jpg"
        timestamp = start + span * (index + 0.5) / count
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-y", "-ss", str(timestamp), "-i", str(clip),
             "-frames:v", "1", "-vf", scale, str(target)],
            check=True,
        )
        paths.append((target, timestamp))
    return paths
```

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_media.py tests/test_pipeline.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dashpi/media.py tests/test_media.py
git commit -m "feat: sample frames from a window and cap the long edge"
```

---

### Task 4: OpenAI 호환 클라이언트와 설정 파일

**Files:**
- Create: `src/dashpi/ai_client.py`, `tests/conftest.py`
- Test: `tests/test_ai_client.py`

**Interfaces:**
- Produces:
  - `class AnalysisError(Exception)` — 자동 재시도하지 않는 실패.
  - `class RetryableAnalysisError(Exception)` — `__init__(self, message: str, retry_at: datetime | None = None)`, 속성 `retry_at`.
  - `@dataclass(frozen=True) class AIConfig: api_key: str; base_url: str; daily_limit: int`
  - `DEFAULT_CONFIG_PATH: Path`, `DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"`
  - `load_ai_config(path: Path = DEFAULT_CONFIG_PATH, environ: Mapping[str, str] = os.environ) -> AIConfig` — 키가 없으면 `RetryableAnalysisError("API 키 없음")`.
  - `retry_delay(attempt: int) -> timedelta` — 1→1분, 2→2분, 3→5분, 4→10분, 5 이상→30분.
  - `class ChatClient(base_url: str, api_key: str, timeout: float = 60.0)` — `complete(model: str, messages: list[dict], schema_name: str, schema: dict, max_tokens: int, reasoning_effort: str = "low") -> tuple[dict, dict]` (파싱된 JSON, `usage`).

- [ ] **Step 1: Write the failing tests**

`tests/conftest.py` (개발자 PC의 실제 키가 테스트에 새지 않게):

```python
import os

import pytest


@pytest.fixture(autouse=True)
def no_real_ai_credentials(monkeypatch):
    for name in [key for key in os.environ if key.startswith("DASHPI_AI_")]:
        monkeypatch.delenv(name)
```

`tests/test_ai_client.py`:

```python
import json
import threading
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from dashpi.ai_client import (
    AnalysisError, ChatClient, RetryableAnalysisError, load_ai_config, retry_delay,
)

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"],
          "additionalProperties": False}


def serve(status, body, seen):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            seen.append((self.path, dict(self.headers), json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            payload = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def completion(content, finish="stop", refusal=None):
    return {"choices": [{"finish_reason": finish, "message": {"content": content, "refusal": refusal}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 3}}


def call(server, **kwargs):
    client = ChatClient(f"http://127.0.0.1:{server.server_port}", "sk-test", timeout=2)
    return client.complete("x-ai/grok-4.7", [{"role": "user", "content": "hi"}], "probe", SCHEMA, 50, **kwargs)


def test_request_forces_schema_privacy_and_limits_and_returns_usage():
    seen = []
    server = serve(200, completion('{"ok": true}'), seen)
    try:
        result, usage = call(server)
    finally:
        server.shutdown()
    path, headers, body = seen[0]
    assert (result, usage["completion_tokens"]) == ({"ok": True}, 3)
    assert path == "/chat/completions" and headers["Authorization"] == "Bearer sk-test"
    assert body["response_format"] == {"type": "json_schema", "json_schema": {"name": "probe", "strict": True, "schema": SCHEMA}}
    assert body["provider"] == {"data_collection": "deny"}
    assert body["max_tokens"] == 50 and body["reasoning"] == {"effort": "low"}


def test_code_fenced_json_is_accepted():
    server = serve(200, completion('```json\n{"ok": false}\n```'), [])
    try:
        assert call(server)[0] == {"ok": False}
    finally:
        server.shutdown()


@pytest.mark.parametrize("status", [408, 429, 500, 502, 503])
def test_transient_http_errors_are_retryable(status):
    server = serve(status, {"error": {"message": "busy"}}, [])
    try:
        with pytest.raises(RetryableAnalysisError, match="일시 오류"):
            call(server)
    finally:
        server.shutdown()


@pytest.mark.parametrize("status,message", [(400, "거부"), (401, "API 키"), (402, "크레딧"), (403, "API 키"), (404, "거부")])
def test_permanent_http_errors_fail(status, message):
    server = serve(status, {"error": {"message": "no"}}, [])
    try:
        with pytest.raises(AnalysisError, match=message):
            call(server)
    finally:
        server.shutdown()


def test_error_object_inside_http_200_is_classified():
    server = serve(200, {"error": {"code": 502, "message": "upstream"}}, [])
    try:
        with pytest.raises(RetryableAnalysisError):
            call(server)
    finally:
        server.shutdown()


@pytest.mark.parametrize("body,message", [
    (completion("{}", refusal="I can't"), "거부"),
    (completion('{"ok": tr', finish="length"), "잘림"),
    (completion("not json"), "형식"),
    (b"<html>", "형식"),
])
def test_unusable_answers_fail(body, message):
    server = serve(200, body, [])
    try:
        with pytest.raises(AnalysisError, match=message):
            call(server)
    finally:
        server.shutdown()


def test_unreachable_server_is_retryable():
    client = ChatClient("http://127.0.0.1:9", "sk-test", timeout=1)
    with pytest.raises(RetryableAnalysisError, match="인터넷"):
        client.complete("m", [], "probe", SCHEMA, 10)


def test_config_file_tolerates_hand_editing(tmp_path):
    path = tmp_path / "ai.env"
    path.write_bytes(b'# DashPi\r\nexport DASHPI_AI_API_KEY = "sk-or-1"\r\n\r\nDASHPI_AI_DAILY_LIMIT=5\r\n')
    path.chmod(0o600)
    config = load_ai_config(path, environ={})
    assert (config.api_key, config.base_url, config.daily_limit) == ("sk-or-1", "https://openrouter.ai/api/v1", 5)


def test_environment_overrides_file_and_missing_key_waits(tmp_path):
    assert load_ai_config(tmp_path / "none", environ={"DASHPI_AI_API_KEY": "sk-env"}).api_key == "sk-env"
    with pytest.raises(RetryableAnalysisError, match="API 키 없음"):
        load_ai_config(tmp_path / "none", environ={})


def test_non_https_remote_base_url_is_rejected(tmp_path):
    with pytest.raises(AnalysisError, match="base URL"):
        load_ai_config(tmp_path / "none", environ={"DASHPI_AI_API_KEY": "k", "DASHPI_AI_BASE_URL": "http://example.com/v1"})


def test_world_readable_key_file_logs_a_warning(tmp_path, caplog):
    path = tmp_path / "ai.env"
    path.write_text("DASHPI_AI_API_KEY=sk\n")
    path.chmod(0o644)
    load_ai_config(path, environ={})
    assert "chmod 600" in caplog.text


def test_retry_delays_follow_the_schedule():
    assert [retry_delay(n) for n in (1, 2, 3, 4, 5, 9)] == [
        timedelta(minutes=m) for m in (1, 2, 5, 10, 30, 30)
    ]
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_ai_client.py`
Expected: FAIL (`No module named 'dashpi.ai_client'`)

- [ ] **Step 3: Implement `src/dashpi/ai_client.py`**

```python
"""OpenAI-compatible chat client for incident analysis (OpenRouter by default)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
import ipaddress
import json
import logging
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger("dashpi")

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_CONFIG_PATH = Path.home() / ".config" / "dashpi" / "ai.env"
DEFAULT_DAILY_LIMIT = 20
_RETRY_MINUTES = (1, 2, 5, 10, 30)
_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.S)


class AnalysisError(Exception):
    """Analysis failed in a way retrying will not fix; the evidence clip stays preserved."""


class RetryableAnalysisError(Exception):
    """Analysis could not run now (offline, provider busy, no key, daily limit); try again later."""

    def __init__(self, message: str, retry_at: datetime | None = None):
        super().__init__(message)
        self.retry_at = retry_at


@dataclass(frozen=True)
class AIConfig:
    api_key: str
    base_url: str
    daily_limit: int


def retry_delay(attempt: int) -> timedelta:
    return timedelta(minutes=_RETRY_MINUTES[min(max(attempt, 1), len(_RETRY_MINUTES)) - 1])


def _read_env_file(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    if path.stat().st_mode & 0o077:
        log.warning("AI 키 파일 권한이 넓습니다: chmod 600 %s", path)
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def _valid_base_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    loopback = False
    try:
        loopback = parsed.hostname is not None and ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        pass
    if parsed.scheme == "https" or (parsed.scheme == "http" and loopback):
        return url.rstrip("/")
    raise AnalysisError("AI base URL은 https여야 합니다")


def load_ai_config(path: Path = DEFAULT_CONFIG_PATH, environ: Mapping[str, str] = os.environ) -> AIConfig:
    values = _read_env_file(path)
    values.update({key: value for key, value in environ.items() if key.startswith("DASHPI_AI_")})
    api_key = values.get("DASHPI_AI_API_KEY", "").strip()
    if not api_key:
        raise RetryableAnalysisError("API 키 없음")
    try:
        daily_limit = int(values.get("DASHPI_AI_DAILY_LIMIT", DEFAULT_DAILY_LIMIT))
    except ValueError as error:
        raise AnalysisError("DASHPI_AI_DAILY_LIMIT 값이 숫자가 아닙니다") from error
    return AIConfig(api_key, _valid_base_url(values.get("DASHPI_AI_BASE_URL", DEFAULT_BASE_URL)), daily_limit)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def _http_error(status: int) -> Exception:
    if status in (408, 429) or status >= 500:
        return RetryableAnalysisError(f"분석 서버 일시 오류 (HTTP {status})")
    if status in (401, 403):
        return AnalysisError(f"API 키 확인 필요 (HTTP {status})")
    if status == 402:
        return AnalysisError("크레딧 부족 (HTTP 402)")
    return AnalysisError(f"분석 요청 거부 (HTTP {status})")


class ChatClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 60.0):
        self.base_url, self.api_key, self.timeout = base_url.rstrip("/"), api_key, timeout
        self.opener = urllib.request.build_opener(_NoRedirect())  # env proxies still apply

    def complete(self, model: str, messages: list[dict], schema_name: str, schema: dict,
                 max_tokens: int, reasoning_effort: str = "low") -> tuple[dict, dict]:
        body = json.dumps({
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "reasoning": {"effort": reasoning_effort},
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": schema_name, "strict": True, "schema": schema}},
            "provider": {"data_collection": "deny"},
        }).encode()
        request = urllib.request.Request(
            self.base_url + "/chat/completions", data=body,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
                     "X-Title": "DashPi"},
        )
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = json.loads(response.read())
        except urllib.error.HTTPError as error:
            raise _http_error(error.code) from error
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as error:
            raise RetryableAnalysisError("인터넷 연결 없음") from error
        except ValueError as error:
            raise AnalysisError("응답 형식 오류") from error
        return self._parse(raw)

    @staticmethod
    def _parse(raw: object) -> tuple[dict, dict]:
        if not isinstance(raw, dict):
            raise AnalysisError("응답 형식 오류")
        if isinstance(raw.get("error"), dict):
            code = raw["error"].get("code")
            raise _http_error(code if isinstance(code, int) else 400)
        try:
            choice = raw["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError, TypeError) as error:
            raise AnalysisError("응답 형식 오류") from error
        if message.get("refusal"):
            raise AnalysisError("모델이 분석을 거부했습니다")
        if choice.get("finish_reason") == "length":
            raise AnalysisError("응답이 잘림 (max_tokens 부족)")
        content = message.get("content") or ""
        fenced = _FENCE.match(content)
        try:
            parsed = json.loads(fenced.group(1) if fenced else content)
        except ValueError as error:
            raise AnalysisError("응답 형식 오류") from error
        if not isinstance(parsed, dict):
            raise AnalysisError("응답 형식 오류")
        return parsed, raw.get("usage") or {}
```

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_ai_client.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dashpi/ai_client.py tests/test_ai_client.py
git commit -m "feat: add OpenAI-compatible analysis client with error classification"
```

---

### Task 5: 하루 분석 한도

**Files:**
- Create: `src/dashpi/ai_budget.py`
- Test: `tests/test_ai_budget.py`

**Interfaces:**
- Consumes: `RetryableAnalysisError(message, retry_at)` (Task 4), `atomic_write` (`dashpi.storage`).
- Produces: `DailyBudget(path: Path, limit: int, now: Callable[[], datetime] = lambda: datetime.now().astimezone())` — `consume() -> None`는 한도 안이면 1 증가, 넘으면 `RetryableAnalysisError("오늘 분석 한도 도달", retry_at=다음 날 00:05 현지)`.

- [ ] **Step 1: Write the failing tests**

```python
from datetime import datetime, timedelta, timezone

import pytest

from dashpi.ai_budget import DailyBudget
from dashpi.ai_client import RetryableAnalysisError

KST = timezone(timedelta(hours=9))


def test_limit_blocks_until_five_past_midnight_next_day(tmp_path):
    now = datetime(2026, 9, 25, 22, 0, tzinfo=KST)
    budget = DailyBudget(tmp_path / "ai-usage.json", 2, lambda: now)
    budget.consume()
    budget.consume()
    with pytest.raises(RetryableAnalysisError, match="한도") as error:
        budget.consume()
    assert error.value.retry_at == datetime(2026, 9, 26, 0, 5, tzinfo=KST)


def test_count_resets_on_a_new_day(tmp_path):
    clock = [datetime(2026, 9, 25, 23, 0, tzinfo=KST)]
    budget = DailyBudget(tmp_path / "ai-usage.json", 1, lambda: clock[0])
    budget.consume()
    clock[0] += timedelta(hours=2)
    budget.consume()


def test_corrupt_usage_file_starts_fresh(tmp_path):
    path = tmp_path / "ai-usage.json"
    path.write_text("{not json")
    DailyBudget(path, 1, lambda: datetime(2026, 9, 25, tzinfo=KST)).consume()
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_ai_budget.py`
Expected: FAIL (module missing)

- [ ] **Step 3: Implement `src/dashpi/ai_budget.py`**

```python
"""Per-device daily cap on analyses — the second line of defence behind the provider key limit."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, time, timedelta
import json
from pathlib import Path

from dashpi.ai_client import RetryableAnalysisError
from dashpi.storage import atomic_write


class DailyBudget:
    def __init__(self, path: Path, limit: int,
                 now: Callable[[], datetime] = lambda: datetime.now().astimezone()):
        self.path, self.limit, self.now = path, limit, now

    def consume(self) -> None:
        now = self.now()
        today = now.date().isoformat()
        try:
            raw = json.loads(self.path.read_text())
            count = raw["count"] if raw.get("date") == today and isinstance(raw.get("count"), int) else 0
        except (OSError, ValueError, AttributeError):
            count = 0
        if count >= self.limit:
            resume = datetime.combine(now.date() + timedelta(days=1), time(0, 5), tzinfo=now.tzinfo)
            raise RetryableAnalysisError("오늘 분석 한도 도달", retry_at=resume)
        atomic_write(self.path, json.dumps({"date": today, "count": count + 1}).encode())
```

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_ai_budget.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dashpi/ai_budget.py tests/test_ai_budget.py
git commit -m "feat: cap analyses per day on the device"
```

---

### Task 6: 분석 역할과 `Analyzer`

**Files:**
- Create: `src/dashpi/analysis.py`
- Test: `tests/test_analysis.py`

**Interfaces:**
- Consumes: `ChatClient.complete(...) -> (dict, usage)`, `load_ai_config`, `AnalysisError`, `RetryableAnalysisError`, `DEFAULT_CONFIG_PATH` (Task 4); `DailyBudget` (Task 5); `sample_frames(clip, dir, count, start, end)` (Task 3); `probe_duration` (`dashpi.media`).
- Produces:
  - `FAKE_MODEL = "fake"`, `OBSERVE_SECONDS = 3.0`, `MAX_TOKENS = {"locate": 300, "observe": 1500, "report": 1200}`
  - `@dataclass(frozen=True) class RoleResult: output: dict; usage: dict; seconds: float; model: str`
  - `locate(client, model, frames: list[tuple[Path, float]]) -> RoleResult` (output: `incident_timestamp`, `confidence`, `reason`)
  - `observe(client, model, frames) -> RoleResult` (output: `observations`)
  - `summarize(client, model, observations: list[dict]) -> RoleResult` (output: `summary`, `limitations`)
  - `observe_window(moment: float, duration: float) -> tuple[float, float]`
  - `class Analyzer(vision_model: str, report_model: str, data_root: Path, config_path: Path = DEFAULT_CONFIG_PATH, client_factory=ChatClient)` — `__call__(frames, clip_path: Path, frame_dir: Path, incident_offset_override: float | None = None) -> dict` 반환 dict는 `incident_timestamp, summary, observations, limitations, analysis`.
  - `class FakeAnalyzer` — 같은 `__call__` 시그니처.
  - `build_analyzer(vision_model: str, report_model: str, data_root: Path) -> Analyzer | FakeAnalyzer`
  - `api_key_configured(config_path: Path = DEFAULT_CONFIG_PATH) -> bool`

- [ ] **Step 1: Write the failing tests**

```python
import pytest

from dashpi.ai_client import AnalysisError, RetryableAnalysisError
from dashpi.analysis import Analyzer, FakeAnalyzer, build_analyzer, observe_window
from dashpi.reports import validate_report
from tests.media_factory import make_video


class ScriptedClient:
    """Stands in for ChatClient; answers each role from a script and records requests."""

    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def complete(self, model, messages, schema_name, schema, max_tokens, reasoning_effort="low"):
        self.calls.append((schema_name, model, messages, max_tokens))
        answer = self.answers[schema_name]
        if isinstance(answer, Exception):
            raise answer
        return answer, {"prompt_tokens": 100, "completion_tokens": 10}


ANSWERS = {
    "locate": {"incident_timestamp": 4.0, "confidence": 0.8, "reason": "앞차 급정거"},
    "observe": {"observations": [{"timestamp": 3.5, "description": "앞차 브레이크등 점등"}]},
    "report": {"summary": "앞차가 급정거했다.", "limitations": ["야간 화질 저하"]},
}


def analyzer(tmp_path, client, key="sk"):
    config = tmp_path / "ai.env"
    config.write_text(f"DASHPI_AI_API_KEY={key}\n")
    config.chmod(0o600)
    return Analyzer("vision-m", "report-m", tmp_path, config_path=config,
                    client_factory=lambda *_args, **_kw: client)


def frames_for(clip, tmp_path):
    from dashpi.media import sample_frames
    return sample_frames(clip, tmp_path / "frames", 12)


def test_roles_run_in_order_and_result_passes_report_validation(tmp_path):
    clip = make_video(tmp_path / "clip.mp4", 8)
    client = ScriptedClient(ANSWERS)
    result = analyzer(tmp_path, client)(frames_for(clip, tmp_path), clip, tmp_path / "work")

    assert [name for name, *_ in client.calls] == ["locate", "observe", "report"]
    assert [model for _name, model, *_ in client.calls] == ["vision-m", "vision-m", "report-m"]
    assert result["analysis"]["locate"] == {"confidence": 0.8, "reason": "앞차 급정거"}
    raw = {key: result[key] for key in ("incident_timestamp", "summary", "observations", "limitations")}
    assert validate_report(raw, "0" * 64, "label", "now", 8.0)["incident_timestamp"] == 4.0


def test_observe_frames_come_from_the_window_around_the_moment(tmp_path):
    clip = make_video(tmp_path / "clip.mp4", 8)
    client = ScriptedClient(ANSWERS)
    analyzer(tmp_path, client)(frames_for(clip, tmp_path), clip, tmp_path / "work")

    observe_text = " ".join(part["text"] for part in client.calls[1][2][1]["content"] if part["type"] == "text")
    stamps = [float(token.removesuffix("초")) for token in observe_text.split() if token.endswith("초")]
    assert len(stamps) == 12 and min(stamps) >= 1.0 and max(stamps) <= 7.0


def test_role_timing_and_tokens_are_logged_without_the_key(tmp_path, caplog):
    import logging
    caplog.set_level(logging.INFO, logger="dashpi")
    clip = make_video(tmp_path / "clip.mp4", 8)
    analyzer(tmp_path, ScriptedClient(ANSWERS), key="sk-secret")(frames_for(clip, tmp_path), clip, tmp_path / "w")
    assert "AI observe: vision-m" in caplog.text and "토큰 100/10" in caplog.text
    assert "sk-secret" not in caplog.text


def test_manual_moment_skips_locating(tmp_path):
    clip = make_video(tmp_path / "clip.mp4", 8)
    client = ScriptedClient(ANSWERS)
    result = analyzer(tmp_path, client)(frames_for(clip, tmp_path), clip, tmp_path / "work", 2.5)

    assert [name for name, *_ in client.calls] == ["observe", "report"]
    assert result["incident_timestamp"] == 2.5


def test_missing_key_waits_before_any_call_or_budget_use(tmp_path):
    clip = make_video(tmp_path / "clip.mp4", 4)
    client = ScriptedClient(ANSWERS)
    with pytest.raises(RetryableAnalysisError, match="API 키"):
        analyzer(tmp_path, client, key="")(frames_for(clip, tmp_path), clip, tmp_path / "w")
    assert client.calls == [] and not (tmp_path / "ai-usage.json").exists()


def test_locate_answer_outside_the_clip_fails(tmp_path):
    clip = make_video(tmp_path / "clip.mp4", 4)
    client = ScriptedClient({**ANSWERS, "locate": {"incident_timestamp": 99.0, "confidence": 1.0, "reason": "x"}})
    with pytest.raises(AnalysisError, match="사고 시각"):
        analyzer(tmp_path, client)(frames_for(clip, tmp_path), clip, tmp_path / "w")


@pytest.mark.parametrize("moment,duration,expected", [
    (4.0, 8.0, (1.0, 7.0)),
    (0.2, 8.0, (0.0, 3.2)),
    (7.9, 8.0, (4.9, 8.0)),
    (0.3, 0.6, (0.0, 0.6)),
])
def test_observe_window_stays_inside_the_clip(moment, duration, expected):
    assert observe_window(moment, duration) == pytest.approx(expected)


def test_fake_model_needs_no_network_and_validates(tmp_path):
    clip = make_video(tmp_path / "clip.mp4", 6)
    fake = build_analyzer("fake", "anything", tmp_path)
    assert isinstance(fake, FakeAnalyzer)
    result = fake([], clip, tmp_path / "w")
    raw = {key: result[key] for key in ("incident_timestamp", "summary", "observations", "limitations")}
    validate_report(raw, "0" * 64, "fake", "now", 6.0)
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_analysis.py`
Expected: FAIL (module missing)

- [ ] **Step 3: Implement `src/dashpi/analysis.py`**

```python
"""Incident analysis in three gradeable roles: locate the moment, observe the scene, summarize."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import logging
import math
from pathlib import Path
import time

from dashpi.ai_budget import DailyBudget
from dashpi.ai_client import (
    DEFAULT_CONFIG_PATH, AnalysisError, ChatClient, RetryableAnalysisError, load_ai_config,
)
from dashpi.media import probe_duration, sample_frames

log = logging.getLogger("dashpi")
FAKE_MODEL = "fake"
OBSERVE_SECONDS = 3.0
FRAME_COUNT = 12
MAX_TOKENS = {"locate": 300, "observe": 1500, "report": 1200}
RULES = (
    "당신은 블랙박스 사고 영상 분석 보조입니다. 화면에 보이는 사실만 쓰고, 보이지 않는 것은 추측하지 마세요. "
    "법적 과실이나 책임을 판단하지 마세요. 모든 문장은 한국어로 쓰세요."
)


def _object(properties: dict) -> dict:
    return {"type": "object", "properties": properties, "required": list(properties),
            "additionalProperties": False}


LOCATE_SCHEMA = _object({
    "incident_timestamp": {"type": "number"},
    "confidence": {"type": "number"},
    "reason": {"type": "string"},
})
OBSERVE_SCHEMA = _object({
    "observations": {"type": "array", "items": _object({
        "timestamp": {"type": "number"}, "description": {"type": "string"},
    })},
})
REPORT_SCHEMA = _object({
    "summary": {"type": "string"},
    "limitations": {"type": "array", "items": {"type": "string"}},
})


@dataclass(frozen=True)
class RoleResult:
    output: dict
    usage: dict
    seconds: float
    model: str


def _frame_content(instruction: str, frames: list[tuple[Path, float]]) -> list[dict]:
    content = [{"type": "text", "text": instruction}]
    for path, timestamp in frames:
        content.append({"type": "text", "text": f"{timestamp:.2f}초"})
        encoded = base64.b64encode(path.read_bytes()).decode()
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}})
    return content


def _run(client, model: str, name: str, schema: dict, content) -> RoleResult:
    started = time.monotonic()
    output, usage = client.complete(
        model, [{"role": "system", "content": RULES}, {"role": "user", "content": content}],
        name, schema, MAX_TOKENS[name],
    )
    return RoleResult(output, usage, time.monotonic() - started, model)


def locate(client, model: str, frames: list[tuple[Path, float]]) -> RoleResult:
    instruction = ("각 이미지 앞의 숫자는 증거 클립 시작(0초) 기준 시각입니다. 충돌·급정거·급회피 등 사고 순간의 "
                   "시각(초)을 incident_timestamp로, 확신도(0~1)를 confidence로, 짧은 근거를 reason으로 답하세요.")
    return _run(client, model, "locate", LOCATE_SCHEMA, _frame_content(instruction, frames))


def observe(client, model: str, frames: list[tuple[Path, float]]) -> RoleResult:
    instruction = ("사고 순간 전후 프레임입니다. 차량·보행자·신호·차선·도로·날씨·움직임에 대해 보이는 사실을 "
                   "시각(초, 클립 기준)과 함께 observations로 나열하세요. 판단이나 추측은 쓰지 마세요.")
    return _run(client, model, "observe", OBSERVE_SCHEMA, _frame_content(instruction, frames))


def summarize(client, model: str, observations: list[dict]) -> RoleResult:
    instruction = ("다음 관찰 목록만 근거로 운전자가 읽을 사고 요약(summary)과 이 분석의 한계(limitations)를 쓰세요. "
                   "관찰에 없는 사실·숫자·고유명사를 추가하지 마세요.\n"
                   + json.dumps(observations, ensure_ascii=False))
    return _run(client, model, "report", REPORT_SCHEMA, instruction)


def observe_window(moment: float, duration: float) -> tuple[float, float]:
    start = max(0.0, moment - OBSERVE_SECONDS)
    end = min(duration, moment + OBSERVE_SECONDS)
    return (0.0, duration) if end - start < 1.0 else (start, end)


class Analyzer:
    def __init__(self, vision_model: str, report_model: str, data_root: Path,
                 config_path: Path = DEFAULT_CONFIG_PATH, client_factory=ChatClient):
        self.vision_model, self.report_model = vision_model, report_model
        self.data_root, self.config_path, self.client_factory = data_root, config_path, client_factory

    def __call__(self, frames, clip_path: Path, frame_dir: Path,
                 incident_offset_override: float | None = None) -> dict:
        config = load_ai_config(self.config_path)  # re-read so a key added later is picked up
        DailyBudget(self.data_root / "ai-usage.json", config.daily_limit).consume()
        client = self.client_factory(config.base_url, config.api_key)
        duration = probe_duration(clip_path)
        steps = []
        if incident_offset_override is None:
            located = locate(client, self.vision_model, frames)
            moment = located.output["incident_timestamp"]
            if isinstance(moment, bool) or not isinstance(moment, (int, float)) \
                    or not math.isfinite(moment) or not 0.0 <= moment <= duration:
                raise AnalysisError("모델이 준 사고 시각이 클립 밖입니다")
            steps.append(("locate", located))
        else:
            moment = incident_offset_override
        start, end = observe_window(moment, duration)
        dense = sample_frames(clip_path, frame_dir / "observe", FRAME_COUNT, start, end)
        observed = observe(client, self.vision_model, dense)
        reported = summarize(client, self.report_model, observed.output["observations"])
        steps += [("observe", observed), ("report", reported)]
        for name, result in steps:  # never log the key or image content
            log.info("AI %s: %s %.1fs 토큰 %s/%s", name, result.model, result.seconds,
                     result.usage.get("prompt_tokens"), result.usage.get("completion_tokens"))
        analysis = {
            "models": {name: result.model for name, result in steps},
            "usage": {name: result.usage for name, result in steps},
            "seconds": {name: round(result.seconds, 2) for name, result in steps},
        }
        if incident_offset_override is None:
            analysis["locate"] = {key: steps[0][1].output[key] for key in ("confidence", "reason")}
        return {
            "incident_timestamp": moment,
            "summary": reported.output["summary"],
            "observations": observed.output["observations"],
            "limitations": reported.output["limitations"],
            "analysis": analysis,
        }


class FakeAnalyzer:
    """Deterministic offline stand-in so teammates can exercise the whole flow for free."""

    def __call__(self, frames, clip_path: Path, frame_dir: Path,
                 incident_offset_override: float | None = None) -> dict:
        duration = probe_duration(clip_path)
        moment = duration / 2 if incident_offset_override is None else incident_offset_override
        return {
            "incident_timestamp": moment,
            "summary": "가짜 분석기 결과입니다. 실제 영상 내용이 아닙니다.",
            "observations": [{"timestamp": moment, "description": "가짜 관찰"}],
            "limitations": ["테스트용 가짜 분석 결과"],
            "analysis": {"models": {"all": FAKE_MODEL}},
        }


def build_analyzer(vision_model: str, report_model: str, data_root: Path):
    if vision_model == FAKE_MODEL:
        return FakeAnalyzer()
    return Analyzer(vision_model, report_model, data_root)


def api_key_configured(config_path: Path = DEFAULT_CONFIG_PATH) -> bool:
    try:
        load_ai_config(config_path)
        return True
    except (RetryableAnalysisError, AnalysisError):
        return False
```

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_analysis.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dashpi/analysis.py tests/test_analysis.py
git commit -m "feat: split incident analysis into locate, observe and summarize roles"
```

---

### Task 7: 파이프라인 — 새 분석 인자와 "분석 대기" 전이

**Files:**
- Modify: `src/dashpi/pipeline.py:110-240`, `src/dashpi/reports.py` (`OllamaClient.analyze` 시그니처만 임시 확장)
- Test: `tests/test_pipeline.py`와 분석 함수를 흉내 내는 모든 테스트

**Interfaces:**
- Consumes: `RetryableAnalysisError.retry_at`, `retry_delay` (Task 4); `sample_frames(..., max_edge=1024)` 기본값 (Task 3).
- Produces: 파이프라인은 `analyze(frames, clip_path, frame_dir, incident_offset_override)`를 호출한다. 반환 dict의 `"analysis"` 키는 검증 전에 떼어 `report["analysis"]`에 보존한다. 재시도 가능 오류 → `AWAITING_ANALYSIS`, `analysis_attempts += 1`, `next_analysis_at = (retry_at 또는 now + retry_delay(attempts)).isoformat()`. `READY` 전이 시 `next_analysis_at = None`.

- [ ] **Step 1: Write the failing tests** (`tests/test_pipeline.py`에 추가)

```python
def test_retryable_failure_waits_with_backoff_and_keeps_clip(pipeline_fixture):
    from datetime import datetime
    from dashpi.ai_client import RetryableAnalysisError

    pipeline, incident, segments = pipeline_fixture

    def offline(*_args):
        raise RetryableAnalysisError("인터넷 연결 없음")

    result = pipeline.process(incident, segments, offline)

    assert result.state is IncidentState.AWAITING_ANALYSIS
    assert (result.failure_reason, result.analysis_attempts) == ("인터넷 연결 없음", 1)
    waited = datetime.fromisoformat(result.next_analysis_at) - datetime.fromisoformat(result.transitions[-1]["at"])
    assert 55 <= waited.total_seconds() <= 65
    assert result.clip.path.exists()


def test_retry_at_from_the_error_wins(pipeline_fixture):
    from datetime import UTC, datetime
    from dashpi.ai_client import RetryableAnalysisError

    pipeline, incident, segments = pipeline_fixture
    tomorrow = datetime(2030, 1, 1, 0, 5, tzinfo=UTC)

    def limited(*_args):
        raise RetryableAnalysisError("오늘 분석 한도 도달", retry_at=tomorrow)

    assert pipeline.process(incident, segments, limited).next_analysis_at == tomorrow.isoformat()


def test_analyzer_receives_clip_and_its_extra_analysis_is_kept(pipeline_fixture):
    pipeline, incident, segments = pipeline_fixture
    seen = {}

    def analyze(frames, clip_path, frame_dir, override):
        seen.update(frames=len(frames), clip=clip_path.name, override=override)
        return {"incident_timestamp": 3.0, "summary": "s", "observations": [], "limitations": [],
                "analysis": {"models": {"observe": "m"}}}

    result = pipeline.process(incident, segments, analyze)

    assert seen == {"frames": 12, "clip": "clip.mp4", "override": None}
    assert json.loads(result.report_json.path.read_text())["analysis"] == {"models": {"observe": "m"}}
    assert result.next_analysis_at is None
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_pipeline.py -k "retry or analysis_is_kept"`
Expected: FAIL

- [ ] **Step 3: Implement**

`src/dashpi/pipeline.py` 상단 import에 추가:

```python
from datetime import timedelta  # (UTC, datetime은 이미 import됨)
from dashpi.ai_client import RetryableAnalysisError, retry_delay
```

`generate_report`의 분석 부분을 바꾼다:

```python
            frames = sample_frames(evidence_path, directory / "frames", self.settings.frame_sample_count)
            generated_at = datetime.now(UTC).isoformat()
            self.wait_for_capacity()
            raw = analyze(frames, evidence_path, directory, incident_offset_override)
            analysis = raw.pop("analysis", None) if isinstance(raw, dict) else None
            report = validate_report(
                raw,
                incident.clip.sha256,
                self.settings.report_model_label,
                generated_at,
                incident.clip.duration,
                incident_offset_override,
            )
            if analysis is not None:
                report["analysis"] = analysis
```

`READY` 전이 직전에 `incident.next_analysis_at = None`을 넣고, 마지막 `except`를 두 갈래로 나눈다:

```python
            incident.next_analysis_at = None
            incident.transition(IncidentState.READY, datetime.now(UTC).isoformat())
        except RetryableAnalysisError as error:
            now = datetime.now(UTC)
            incident.analysis_attempts += 1
            retry_at = error.retry_at or now + retry_delay(incident.analysis_attempts)
            incident.next_analysis_at = retry_at.isoformat()
            incident.transition(IncidentState.AWAITING_ANALYSIS, now.isoformat(), str(error))
        except Exception as error:
            incident.transition(IncidentState.ANALYSIS_FAILED, datetime.now(UTC).isoformat(), str(error))
```

`src/dashpi/reports.py`의 `OllamaClient.analyze(self, frames)` → `analyze(self, frames, *_context)` (Task 9에서 삭제될 때까지 호환).

분석 함수를 흉내 내는 테스트의 인자를 넓힌다:

```bash
grep -rln "lambda frames:\|lambda _frames:\|def fail(_frames)\|def analyze(frames)\|def analyze(_frames)\|lambda _: {}\|lambda frames: {}" tests
```

각 파일에서 `lambda frames:`/`lambda _frames:`/`lambda _:` → `lambda *_:`, `def fail(_frames):` → `def fail(*_args):`, `def analyze(frames):`/`def analyze(_frames):` → `def analyze(*_args):`, `def analyze(self, _frames)` → `def analyze(self, *_args)`로 바꾼다. `tests/test_regeneration.py`의 `lambda path, *_:` sample_frames 대체는 그대로 둔다(인자 개수와 무관). `tests/test_desktop.py:156`의 `session.analyze = lambda _frames: {}` → `lambda *_: {}`.

- [ ] **Step 4: Run all tests**

Run: `PYTHONPATH=src QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dashpi/pipeline.py src/dashpi/reports.py tests
git commit -m "feat: hand analyzers the evidence clip and wait on retryable failures"
```

---

### Task 8: 분석 대기 재시도기

**Files:**
- Create: `src/dashpi/analysis_retry.py`
- Test: `tests/test_analysis_retry.py`

**Interfaces:**
- Consumes: `IncidentStore.list(states=...)/load()/save()` (Task 2 fix: `list()` defaults to summary states; pass `states=set(IncidentState)` to see ANALYZING), `IncidentState.AWAITING_ANALYSIS/ANALYZING/ANALYSIS_FAILED`, `IncidentMetadata.next_analysis_at` (Task 2).
- Produces: `AnalysisRetrier(store: IncidentStore, run: Callable[[str], Future], now: Callable[[], datetime] = lambda: datetime.now(UTC))` — `recover_interrupted() -> list[str]`(앱 시작 시 `analyzing` → 대기, 즉시 대상), `tick() -> str | None`(대상 하나를 `run(incident_id)`로 제출하고 id 반환; 실행 중이면 `None`). 직전 실행이 예외로 끝나면 그 사고를 `analysis_failed`로 바꾼다.

- [ ] **Step 1: Write the failing tests**

```python
from concurrent.futures import Future
from datetime import UTC, datetime, timedelta

from dashpi.analysis_retry import AnalysisRetrier
from dashpi.models import IncidentMetadata, IncidentState
from dashpi.storage import IncidentStore

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)


def awaiting(store, incident_id, due, state=IncidentState.AWAITING_ANALYSIS):
    item = IncidentMetadata.new(incident_id, NOW.isoformat(), 10.0, 15.0)
    item.next_analysis_at = None if due is None else due.isoformat()
    item.transition(state, NOW.isoformat(), "인터넷 연결 없음")
    store.save(item)


def test_due_incidents_run_one_at_a_time_earliest_first(tmp_path):
    store = IncidentStore(tmp_path)
    awaiting(store, "later", NOW - timedelta(minutes=1))
    awaiting(store, "first", NOW - timedelta(minutes=5))
    awaiting(store, "future", NOW + timedelta(minutes=5))
    submitted, pending = [], Future()
    retrier = AnalysisRetrier(store, lambda incident_id: submitted.append(incident_id) or pending, lambda: NOW)

    assert retrier.tick() == "first"
    assert retrier.tick() is None  # still running
    pending.set_result(None)
    assert retrier.tick() == "later"
    assert submitted == ["first", "later"]


def test_mixed_time_zones_are_ordered_by_instant(tmp_path):
    from datetime import timezone
    store = IncidentStore(tmp_path)
    awaiting(store, "utc-later", NOW - timedelta(minutes=1))
    awaiting(store, "kst-earlier", (NOW - timedelta(minutes=30)).astimezone(timezone(timedelta(hours=9))))
    done = Future()
    done.set_result(None)
    assert AnalysisRetrier(store, lambda _id: done, lambda: NOW).tick() == "kst-earlier"


def test_metadata_without_next_time_is_due_immediately(tmp_path):
    store = IncidentStore(tmp_path)
    awaiting(store, "old", None)
    done = Future()
    done.set_result(None)
    assert AnalysisRetrier(store, lambda _id: done, lambda: NOW).tick() == "old"


def test_interrupted_analysis_is_recovered_on_startup(tmp_path):
    store = IncidentStore(tmp_path)
    awaiting(store, "cut", NOW, state=IncidentState.ANALYZING)
    retrier = AnalysisRetrier(store, lambda _id: Future(), lambda: NOW)

    assert retrier.recover_interrupted() == ["cut"]
    loaded = store.load("cut")
    assert loaded.state is IncidentState.AWAITING_ANALYSIS and loaded.next_analysis_at == NOW.isoformat()


def test_run_that_raises_marks_the_incident_failed(tmp_path):
    store = IncidentStore(tmp_path)
    awaiting(store, "broken", NOW - timedelta(seconds=1))
    failed = Future()
    failed.set_exception(ValueError("invalid evidence clip"))
    retrier = AnalysisRetrier(store, lambda _id: failed, lambda: NOW)

    retrier.tick()
    retrier.tick()

    loaded = store.load("broken")
    assert loaded.state is IncidentState.ANALYSIS_FAILED and "invalid evidence clip" in loaded.failure_reason
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_analysis_retry.py`
Expected: FAIL (module missing)

- [ ] **Step 3: Implement `src/dashpi/analysis_retry.py`**

```python
"""Re-run analysis for incidents waiting on network, provider, key, or daily limit."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future
from datetime import UTC, datetime
import logging

from dashpi.models import IncidentState
from dashpi.storage import IncidentStore

log = logging.getLogger("dashpi")


class AnalysisRetrier:
    def __init__(self, store: IncidentStore, run: Callable[[str], Future],
                 now: Callable[[], datetime] = lambda: datetime.now(UTC)):
        self.store, self.run, self.now = store, run, now
        self._running: tuple[str, Future] | None = None

    def recover_interrupted(self) -> list[str]:
        recovered = []
        now = self.now().isoformat()
        for item in self.store.list(states=set(IncidentState)):
            if item.state is IncidentState.ANALYZING:
                item.next_analysis_at = now
                item.transition(IncidentState.AWAITING_ANALYSIS, now, "분석 중 앱이 종료되어 다시 분석합니다")
                self.store.save(item)
                recovered.append(item.incident_id)
        return recovered

    def tick(self) -> str | None:
        if self._running is not None:
            incident_id, future = self._running
            if not future.done():
                return None
            self._running = None
            if future.exception() is not None:
                self._mark_failed(incident_id, future.exception())
        now = self.now()
        due = [
            item for item in self.store.list(states=set(IncidentState))
            if item.state is IncidentState.AWAITING_ANALYSIS
            and (item.next_analysis_at is None or datetime.fromisoformat(item.next_analysis_at) <= now)
        ]
        if not due:
            return None
        earliest = datetime.min.replace(tzinfo=UTC)
        item = min(due, key=lambda entry: datetime.fromisoformat(entry.next_analysis_at)
                   if entry.next_analysis_at else earliest)
        log.info("분석 재시도: %s (%s)", item.incident_id, item.failure_reason)
        self._running = (item.incident_id, self.run(item.incident_id))
        return item.incident_id

    def _mark_failed(self, incident_id: str, error: BaseException) -> None:
        log.error("분석 재시도 실패: %s", incident_id, exc_info=error)
        try:
            item = self.store.load(incident_id)
        except ValueError:
            return
        if item.state in (IncidentState.AWAITING_ANALYSIS, IncidentState.ANALYZING):
            item.transition(IncidentState.ANALYSIS_FAILED, self.now().isoformat(), f"재분석 불가: {error}")
            self.store.save(item)
```

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_analysis_retry.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dashpi/analysis_retry.py tests/test_analysis_retry.py
git commit -m "feat: retry awaiting incident analysis one at a time"
```

---

### Task 9: CLI·웹 서버 연결과 Ollama 제거

**Files:**
- Modify: `src/dashpi/cli.py`, `src/dashpi/server.py`, `src/dashpi/reports.py` (`OllamaClient`, `_NoRedirect`, `_validated_loopback_origin` 삭제)
- Test: `tests/test_cli.py`, `tests/test_server.py`, `tests/test_regeneration.py`, `tests/test_reports.py`

**Interfaces:**
- Consumes: `build_analyzer(vision, report, data_root)`, `FAKE_MODEL` (Task 6); `load_ai_config`, `RetryableAnalysisError` (Task 4).
- Produces: `dashpi simulate ... [--ai-model M] [--ai-report-model M]`; `dashpi-server ... [--ai-model M] [--ai-report-model M]`; `server_module.build_analyzer` 이름(테스트가 교체).

- [ ] **Step 1: Write the failing tests**

`tests/test_cli.py`의 Ollama 테스트 두 개를 다음으로 바꾸고 `from dashpi.reports import OllamaClient`를 지운다:

```python
def test_cli_stops_before_media_work_when_the_api_key_is_missing(tmp_path, monkeypatch):
    from dashpi.ai_client import RetryableAnalysisError

    video = make_video(tmp_path / "source.mp4", 2)
    data_root = tmp_path / "data"
    monkeypatch.setattr("dashpi.cli.load_ai_config", lambda *_: (_ for _ in ()).throw(RetryableAnalysisError("API 키 없음")))
    monkeypatch.setattr(sys, "argv", ["dashpi", "simulate", str(video), "--trigger-seconds", "1",
                                      "--data-root", str(data_root)])

    with pytest.raises(RetryableAnalysisError, match="API 키 없음"):
        main()
    assert not data_root.exists()


def test_cli_fake_model_runs_offline_and_records_window(tmp_path, monkeypatch, capsys):
    video = make_video(tmp_path / "source.mp4", 6)
    from dashpi.config import Settings

    settings = Settings(tmp_path / "data", "fake", pre_seconds=2.0, post_seconds=2.0)
    monkeypatch.setattr("dashpi.cli.Settings", lambda *_args, **_kwargs: settings)
    monkeypatch.setattr(sys, "argv", ["dashpi", "simulate", str(video), "--trigger-seconds", "3",
                                      "--data-root", str(tmp_path / "data"), "--ai-model", "fake"])

    main()

    output = json.loads(capsys.readouterr().out)
    assert (output["pre_seconds"], output["post_seconds"], output["state"]) == (2.0, 2.0, "ready")
```

`tests/test_server.py`: `test_server_accepts_optional_analysis_models_and_overlay_flags`에 `"--ai-report-model", "summary"` 인자와 `assert args.ai_report_model == "summary"`를 추가하고, 파서 기본값 테스트에 `assert args.ai_report_model == "x-ai/grok-4.20"`을 추가한다. `test_server_wires_regeneration_through_the_single_analysis_worker`의 `Client` 클래스 대체를 다음으로 바꾼다:

```python
    monkeypatch.setattr(server_module, "build_analyzer",
                        lambda vision, report, root: captured.setdefault("analyzer", (vision, report, root)) and "analyzer")
```

그리고 `args` Namespace에 `ai_report_model="summary"`를 추가하고, 기존 `Client`에 대한 단언을 `assert captured["analyzer"] == ("vision", "summary", tmp_path)`로 바꾼다.

`tests/test_regeneration.py`의 `run_server`: Namespace에 `ai_report_model="summary"` 추가, `monkeypatch.setattr(server_module, "OllamaClient", ...)` → `monkeypatch.setattr(server_module, "build_analyzer", lambda *_: analyze)`.

`tests/test_reports.py`: `OllamaClient`를 import하거나 사용하는 테스트 함수를 모두 삭제한다(`grep -n "OllamaClient\|_validated_loopback_origin" tests/test_reports.py`로 확인). `validate_report`·`render_report_html` 테스트는 남긴다.

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_cli.py tests/test_server.py tests/test_regeneration.py`
Expected: FAIL (`--ai-report-model` 없음, `build_analyzer` 없음)

- [ ] **Step 3: Implement**

`src/dashpi/cli.py`:

```python
from dashpi.ai_client import load_ai_config
from dashpi.analysis import FAKE_MODEL, build_analyzer
# (OllamaClient import 삭제)

    simulate.add_argument("--ai-model", default="x-ai/grok-4.7")
    simulate.add_argument("--ai-report-model", default="x-ai/grok-4.20")
    ...
    settings = Settings(
        args.data_root, args.ai_model, args.ai_report_model,
        detector_model=args.detector_model,
        ...
    )
    if settings.ai_model != FAKE_MODEL:
        load_ai_config()  # fail before creating media artifacts when no key is configured
    analyzer = build_analyzer(settings.ai_model, settings.ai_report_model, settings.data_root)
    ...
    result = IncidentPipeline(...).process(incident, segments, analyzer)
```

`src/dashpi/server.py`:

```python
from dashpi.analysis import build_analyzer
# (OllamaClient import 삭제)

    parser.add_argument("--ai-model")
    parser.add_argument("--ai-report-model", default="x-ai/grok-4.20")
    ...
    if args.ai_model and args.detector_model:
        settings = Settings(args.data_root, args.ai_model, args.ai_report_model, detector_model=..., overlays=...)
        analyzer = build_analyzer(settings.ai_model, settings.ai_report_model, args.data_root)
        ...
        def regenerate_report(item, offset, overlays):
            incident_id = item.incident_id
            return worker.submit(
                lambda: pipeline.regenerate_report(incident_id, analyzer, offset, overlays)
            )
```

`src/dashpi/reports.py`: `_NoRedirect`, `_validated_loopback_origin`, `OllamaClient`와 그 전용 import(`base64`, `ipaddress`, `urllib.*`)를 삭제한다. `grep -rn "OllamaClient" src tests`가 `desktop.py`만 남겨야 한다(Task 10에서 제거).

- [ ] **Step 4: Run all tests**

Run: `PYTHONPATH=src QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: PASS. `OllamaClient`를 지우면 `desktop.py`의 import가 깨지므로, 이 태스크에서 `desktop.py`도 함께 바꾼다. import를 `from dashpi.analysis import build_analyzer`로 바꾸고 사용처 세 곳을 교체한다(재시도·설정 UI는 Task 10):
- `_begin`: `self.session.analyze = build_analyzer(self.session.settings.ai_model, self.session.settings.ai_report_model, self.settings_path.parent)`
- `_analyze_external`: `analyze = build_analyzer(settings.ai_model, settings.ai_report_model, self.settings_path.parent)`
- `main()`: `build_analyzer(settings.ai_model, settings.ai_report_model, root)`

- [ ] **Step 5: Commit**

```bash
git add src/dashpi/cli.py src/dashpi/server.py src/dashpi/reports.py src/dashpi/desktop.py tests
git commit -m "feat: analyze through build_analyzer in CLI, server and app; drop Ollama"
```

---

### Task 10: Pi 앱 — 재시도 타이머, 설정 두 모델, 대기 표시, 다시 분석

**Files:**
- Modify: `src/dashpi/desktop.py`
- Test: `tests/test_desktop.py`

**Interfaces:**
- Consumes: `AnalysisRetrier` (Task 8), `build_analyzer`, `api_key_configured` (Task 6), `IncidentPipeline.regenerate_report(incident_id, analyze)`.
- Produces: `DashPiWindow.report_model: QLineEdit`, `DashPiWindow.ai_key_status: QLabel`, `DashPiWindow.reanalyze_button: QPushButton`, `DashPiWindow.retrier: AnalysisRetrier | None`, `DashPiWindow._retry_tick()`.

- [ ] **Step 1: Write the failing tests** (`tests/test_desktop.py`에 추가)

```python
def test_settings_edit_both_models_and_show_key_status(qapp, tmp_path, monkeypatch):
    import dashpi.desktop as desktop
    from dashpi.device import load_settings

    monkeypatch.setattr(desktop, "api_key_configured", lambda *_: False)
    window = desktop.DashPiWindow(FakeSession(), IncidentStore(tmp_path), tmp_path / "settings.json")
    try:
        window.show_settings()
        assert (window.model.text(), window.report_model.text()) == ("x-ai/grok-4.7", "x-ai/grok-4.20")
        assert window.ai_key_status.text().startswith("API 키: 없음")
        window.model.setText("fake")
        window.report_model.setText("x-ai/grok-4.3")
        window.save_settings_button.click()
        saved = load_settings(tmp_path / "settings.json")
        assert (saved.ai_model, saved.ai_report_model) == ("fake", "x-ai/grok-4.3")
    finally:
        window.close()


def test_awaiting_incident_detail_explains_the_wait(qapp, tmp_path):
    from dashpi.desktop import DashPiWindow

    store = IncidentStore(tmp_path)
    item = IncidentMetadata.new("wait-1", datetime.now(UTC).isoformat(), 100.0, 15.0)
    item.next_analysis_at = "2026-09-25T05:32:00+00:00"
    item.transition(IncidentState.AWAITING_ANALYSIS, datetime.now(UTC).isoformat(), "인터넷 연결 없음")
    store.save(item)
    window = DashPiWindow(FakeSession(), store, tmp_path / "settings.json")
    try:
        window.show_records()
        window._open_record(window.record_list.item(0))
        assert "분석 대기" in window.report_text.text() and "인터넷 연결 없음" in window.report_text.text()
        assert "다음 시도" in window.report_text.text()
        assert not window.reanalyze_button.isVisible()
    finally:
        window.close()


def test_failed_incident_can_be_queued_for_reanalysis(qapp, tmp_path):
    from dashpi.desktop import DashPiWindow

    store = IncidentStore(tmp_path)
    item = IncidentMetadata.new("fail-1", datetime.now(UTC).isoformat(), 100.0, 15.0)
    item.analysis_attempts = 3
    item.transition(IncidentState.ANALYSIS_FAILED, datetime.now(UTC).isoformat(), "API 키 확인 필요 (HTTP 401)")
    store.save(item)
    window = DashPiWindow(FakeSession(), store, tmp_path / "settings.json")
    try:
        window.showNormal()
        window.show_records()
        window._open_record(window.record_list.item(0))
        assert window.reanalyze_button.isVisible()
        window.reanalyze_button.click()
        loaded = store.load("fail-1")
        assert loaded.state is IncidentState.AWAITING_ANALYSIS
        assert (loaded.analysis_attempts, loaded.next_analysis_at is not None) == (0, True)
        assert not window.reanalyze_button.isVisible()
    finally:
        window.close()
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=src QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_desktop.py -k "both_models or awaiting_incident or reanalysis"`
Expected: FAIL

- [ ] **Step 3: Implement** (`src/dashpi/desktop.py`)

import 추가:

```python
from dashpi.analysis import api_key_configured, build_analyzer
from dashpi.analysis_retry import AnalysisRetrier
from dashpi.pipeline import IncidentPipeline
```

`DashPiWindow.__init__`의 `self.timer.start(100)` 다음에:

```python
        self.retrier = None
        if hasattr(self.session, "worker") and hasattr(self.session, "settings"):
            self.retrier = AnalysisRetrier(self.store, self._run_retry)
            self.retry_timer = QTimer(self)
            self.retry_timer.timeout.connect(self._retry_tick)
            self.retry_timer.start(60_000)
            QTimer.singleShot(0, self._start_retries)
```

메서드 추가:

```python
    def _analyzer(self):
        current = load_settings(self.settings_path)
        return build_analyzer(current.ai_model, current.ai_report_model, self.settings_path.parent)

    def _start_retries(self):
        try:
            self.retrier.recover_interrupted()
        except Exception:
            log.exception("중단된 분석 복구 실패")
        self._retry_tick()

    def _retry_tick(self):
        if self.retrier is None:
            return
        try:
            self.retrier.tick()
        except Exception:
            log.exception("분석 재시도 확인 실패")

    def _run_retry(self, incident_id: str):
        current = load_settings(self.settings_path)
        settings = replace(self.session.settings, ai_model=current.ai_model,
                           ai_report_model=current.ai_report_model)
        pipeline = IncidentPipeline(settings, self.store, getattr(self.session, "detector", None),
                                    wait_for_capacity=self.session.worker.wait_for_capacity)
        analyzer = build_analyzer(current.ai_model, current.ai_report_model, self.settings_path.parent)
        return self.session.worker.submit(lambda: pipeline.regenerate_report(incident_id, analyzer))

    def _reanalyze(self):
        incident = self._selected_incident
        if incident is None:
            return
        try:
            item = self.store.load(incident.incident_id)
        except ValueError:
            return
        if item.state is not IncidentState.ANALYSIS_FAILED:
            return
        now = datetime.now(UTC).isoformat()
        item.analysis_attempts, item.next_analysis_at = 0, now
        item.transition(IncidentState.AWAITING_ANALYSIS, now, "다시 분석 요청")
        self.store.save(item)
        self._selected_incident = item
        self.reanalyze_button.hide()
        self.report_text.setText("분석 대기 · 곧 다시 분석합니다.")
        self._retry_tick()
```

(`from datetime import UTC, datetime` — 기존 `from datetime import datetime`을 바꾼다.)

`_build_settings`: `self.model` 라벨을 "비전 모델"로, 요약 모델 칸과 키 상태 캡션 추가:

```python
        self.model = QLineEdit(current.ai_model)
        self.report_model = QLineEdit(current.ai_report_model)
        ...
        for name, control in (("녹화 화질", self.resolution), ("프레임", self.fps),
                              ("비트레이트", self.quality), ("화면 밝기", self.brightness),
                              ("비전 모델", self.model), ("요약 모델", self.report_model)):
        ...
        self.ai_key_status = QLabel("")
        self.ai_key_status.setObjectName("caption")
        form.addRow(self.ai_key_status)   # storage_usage 행 위
```

`show_settings`의 저장 공간 계산 뒤에:

```python
        self.ai_key_status.setText(
            "API 키: 설정됨" if api_key_configured() else "API 키: 없음 (~/.config/dashpi/ai.env)"
        )
```

`_save_settings`의 `VideoSettings(...)`에 `ai_model=self.model.text().strip(), ai_report_model=self.report_model.text().strip()`.

`_build_detail`: `self.optical_button` 앞에

```python
        self.reanalyze_button = button("다시 분석", self._reanalyze, primary=True)
        self.reanalyze_button.hide()
        layout.addWidget(self.reanalyze_button)
```

`_open_record`: `self.optical_button.setVisible(...)` 다음에
`self.reanalyze_button.setVisible(kind == "incident" and value.state is IncidentState.ANALYSIS_FAILED)`,
그리고 incident 분기의 `if value.state is IncidentState.ANALYSIS_FAILED:` 앞에:

```python
            if value.state is IncidentState.AWAITING_ANALYSIS:
                when = ""
                if value.next_analysis_at:
                    when = f" · 다음 시도 {datetime.fromisoformat(value.next_analysis_at).astimezone():%H:%M}"
                self.report_text.setText(f"분석 대기 · {value.failure_reason or ''}{when}")
            elif value.state is IncidentState.ANALYSIS_FAILED:
                self.report_text.setText(
                    f"AI 분석에 실패했습니다: {value.failure_reason or '알 수 없음'}. 원본 사고 영상은 보존됩니다."
                )
```

(기존 `if value.state is IncidentState.ANALYSIS_FAILED:` 분기는 위 `elif`로 대체하고, 그다음 `elif value.report_json is not None:`은 그대로 둔다.)

`closeEvent`의 `self.timer.stop()` 옆에 `if self.retrier is not None: self.retry_timer.stop()`.

- [ ] **Step 4: Run all tests**

Run: `PYTHONPATH=src QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: PASS (`grep -rn "OllamaClient\|ollama" src`가 비어야 한다)

- [ ] **Step 5: Commit**

```bash
git add src/dashpi/desktop.py tests/test_desktop.py
git commit -m "feat: retry awaiting analyses in the Pi app and allow manual reanalysis"
```

---

### Task 11: 평가 하네스 (`dashpi eval`)

**Files:**
- Create: `src/dashpi/evaluation.py`, `eval/README.md`, `eval/cases/.gitkeep`
- Modify: `src/dashpi/cli.py`
- Test: `tests/test_evaluation.py`

**Interfaces:**
- Consumes: `locate`, `observe`, `summarize`, `observe_window`, `FRAME_COUNT`, `MAX_TOKENS` (Task 6); `ChatClient`, `load_ai_config` (Task 4); `sample_frames`, `probe_duration`.
- Produces:
  - `@dataclass(frozen=True) class Case: case_id: str; clip: Path; expected: dict`
  - `load_cases(root: Path) -> list[Case]` — `clip.mp4`와 `expected.json`이 모두 있는 폴더만.
  - `score(expected: dict, moment: float, observations: list[dict], summary: str, limitations: list[str]) -> dict`
  - `max_cost(case_count: int, vision_models: list[str], report_models: list[str], prices: dict[str, tuple[float, float]]) -> float`
  - `call_cost(usage: dict, price: tuple[float, float]) -> float`
  - `fetch_prices(models: list[str]) -> dict[str, tuple[float, float]]` (OpenRouter `/models`, 토큰당 달러)
  - `run(cases, vision_models, report_models, client, prices, out_path, work_root) -> list[dict]`
  - `summary_table(rows: list[dict]) -> str`

- [ ] **Step 1: Write the failing tests**

```python
import json

import pytest

from dashpi.evaluation import Case, call_cost, load_cases, max_cost, score, summary_table


def test_score_checks_time_recall_and_forbidden_claims():
    expected = {"incident_timestamp": 10.0, "timestamp_tolerance": 1.0,
                "must_observe": ["브레이크등", "빨간불"], "must_not_claim": ["보행자"]}
    result = score(expected, 10.6,
                   [{"timestamp": 9.5, "description": "앞차 브레이크등 점등"}],
                   "앞차가 급정거했고 운전자 과실이다. 속도는 80km였다.", ["야간"])
    assert result["locate_pass"] is True and result["timestamp_error"] == pytest.approx(0.6)
    assert result["observe_recall"] == 0.5
    assert result["report_violations"] == ["과실"]
    assert result["unsupported_numbers"] == ["80"]


def test_score_without_expectations_is_neutral():
    result = score({"incident_timestamp": 3.0}, 9.0, [], "요약", [])
    assert (result["locate_pass"], result["observe_recall"], result["report_violations"]) == (False, 1.0, [])


def test_cost_helpers():
    prices = {"v": (2e-6, 10e-6), "r": (1e-6, 2e-6)}
    assert call_cost({"prompt_tokens": 1000, "completion_tokens": 100}, prices["v"]) == pytest.approx(0.003)
    single = max_cost(1, ["v"], ["r"], prices)
    assert max_cost(10, ["v"], ["r"], prices) == pytest.approx(single * 10)
    assert max_cost(1, ["v", "v"], ["r"], prices) > single


def test_cases_need_both_clip_and_expectations(tmp_path):
    good = tmp_path / "a"
    good.mkdir()
    (good / "clip.mp4").write_bytes(b"x")
    (good / "expected.json").write_text(json.dumps({"incident_timestamp": 1.0}))
    (tmp_path / "no-clip").mkdir()
    (tmp_path / "no-clip" / "expected.json").write_text("{}")
    assert [case.case_id for case in load_cases(tmp_path)] == ["a"]


def test_summary_table_lists_each_combination():
    rows = [{"case": "a", "vision_model": "v", "report_model": "r", "locate_pass": True,
             "observe_recall": 1.0, "report_violations": [], "seconds": 3.2, "cost": 0.05}]
    table = summary_table(rows)
    assert "v" in table and "r" in table and "0.05" in table


def test_eval_command_asks_before_spending(tmp_path, monkeypatch, capsys):
    import sys
    from dashpi import cli

    case = tmp_path / "cases" / "a"
    case.mkdir(parents=True)
    (case / "clip.mp4").write_bytes(b"x")
    (case / "expected.json").write_text(json.dumps({"incident_timestamp": 1.0}))
    monkeypatch.setattr("dashpi.cli.load_ai_config", lambda *_: type("C", (), {"base_url": "https://x", "api_key": "k"})())
    monkeypatch.setattr("dashpi.cli.fetch_prices", lambda models: {m: (1e-6, 1e-6) for m in models})
    monkeypatch.setattr("dashpi.cli.run_evaluation", lambda *_a, **_k: pytest.fail("must not run without consent"))
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")
    monkeypatch.setattr(sys, "argv", ["dashpi", "eval", "--cases", str(tmp_path / "cases"),
                                      "--vision-model", "v", "--report-model", "r", "--out", str(tmp_path / "o.jsonl")])
    with pytest.raises(SystemExit):
        cli.main()
    assert "예상 최대 비용" in capsys.readouterr().out
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_evaluation.py`
Expected: FAIL (module missing)

- [ ] **Step 3: Implement `src/dashpi/evaluation.py`**

```python
"""Evaluation harness: run analysis roles over labelled cases and grade quality, latency, cost."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import time
import urllib.request

from dashpi.analysis import FRAME_COUNT, MAX_TOKENS, locate, observe, observe_window, summarize
from dashpi.media import probe_duration, sample_frames

PRICES_URL = "https://openrouter.ai/api/v1/models"
IMAGE_TOKEN_CEILING = 1100  # per 1024px frame; conservative for max-cost estimates
PROMPT_TOKEN_CEILING = 1000
DEFAULT_FORBIDDEN = ("과실", "책임", "잘못")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


@dataclass(frozen=True)
class Case:
    case_id: str
    clip: Path
    expected: dict


def load_cases(root: Path) -> list[Case]:
    cases = []
    for folder in sorted(path for path in root.iterdir() if path.is_dir()):
        clip, expected = folder / "clip.mp4", folder / "expected.json"
        if clip.is_file() and expected.is_file():
            cases.append(Case(folder.name, clip, json.loads(expected.read_text(encoding="utf-8"))))
    return cases


def score(expected: dict, moment: float, observations: list[dict], summary: str,
          limitations: list[str]) -> dict:
    error = abs(moment - float(expected["incident_timestamp"]))
    observed = " ".join(item["description"] for item in observations)
    must_observe = expected.get("must_observe", [])
    forbidden = list(expected.get("must_not_claim", [])) + list(DEFAULT_FORBIDDEN)
    report_text = " ".join([summary, *limitations])
    return {
        "timestamp_error": error,
        "locate_pass": error <= float(expected.get("timestamp_tolerance", 1.0)),
        "observe_recall": sum(term in observed for term in must_observe) / len(must_observe) if must_observe else 1.0,
        "observe_violations": [term for term in forbidden if term in observed],
        "report_violations": [term for term in forbidden if term in report_text],
        "unsupported_numbers": [n for n in _NUMBER.findall(summary) if n not in observed],
    }


def call_cost(usage: dict, price: tuple[float, float]) -> float:
    return usage.get("prompt_tokens", 0) * price[0] + usage.get("completion_tokens", 0) * price[1]


def max_cost(case_count: int, vision_models: list[str], report_models: list[str],
             prices: dict[str, tuple[float, float]]) -> float:
    vision_input = FRAME_COUNT * IMAGE_TOKEN_CEILING + PROMPT_TOKEN_CEILING
    per_case = 0.0
    for model in vision_models:
        per_case += call_cost({"prompt_tokens": vision_input, "completion_tokens": MAX_TOKENS["locate"]}, prices[model])
        per_case += call_cost({"prompt_tokens": vision_input, "completion_tokens": MAX_TOKENS["observe"]}, prices[model])
        for report in report_models:
            per_case += call_cost({"prompt_tokens": 3 * PROMPT_TOKEN_CEILING,
                                   "completion_tokens": MAX_TOKENS["report"]}, prices[report])
    return per_case * case_count


def fetch_prices(models: list[str]) -> dict[str, tuple[float, float]]:
    with urllib.request.urlopen(PRICES_URL, timeout=30) as response:
        listing = {item["id"]: item["pricing"] for item in json.loads(response.read())["data"]}
    missing = [model for model in models if model not in listing]
    if missing:
        raise ValueError(f"가격을 찾을 수 없는 모델: {', '.join(missing)}")
    return {model: (float(listing[model]["prompt"]), float(listing[model]["completion"])) for model in models}


def run(cases: list[Case], vision_models: list[str], report_models: list[str], client,
        prices: dict[str, tuple[float, float]], out_path: Path, work_root: Path) -> list[dict]:
    rows = []
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a", encoding="utf-8") as out:
        for case in cases:
            duration = probe_duration(case.clip)
            frames = sample_frames(case.clip, work_root / case.case_id / "locate", FRAME_COUNT)
            for vision in vision_models:
                located = locate(client, vision, frames)
                moment = min(max(float(located.output["incident_timestamp"]), 0.0), duration)
                start, end = observe_window(moment, duration)
                dense = sample_frames(case.clip, work_root / case.case_id / f"observe-{start:.2f}", FRAME_COUNT, start, end)
                observed = observe(client, vision, dense)
                for report_model in report_models:
                    reported = summarize(client, report_model, observed.output["observations"])
                    row = {
                        "case": case.case_id, "vision_model": vision, "report_model": report_model,
                        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                        "moment": moment, "locate": located.output,
                        "observations": observed.output["observations"], "report": reported.output,
                        "seconds": round(located.seconds + observed.seconds + reported.seconds, 2),
                        "cost": round(call_cost(located.usage, prices[vision]) + call_cost(observed.usage, prices[vision])
                                      + call_cost(reported.usage, prices[report_model]), 5),
                        **score(case.expected, moment, observed.output["observations"],
                                reported.output["summary"], reported.output["limitations"]),
                    }
                    out.write(json.dumps(row, ensure_ascii=False) + "\n")
                    rows.append(row)
    return rows


def summary_table(rows: list[dict]) -> str:
    lines = ["case\tvision\treport\tlocate\trecall\tviolations\tseconds\tcost"]
    for row in rows:
        lines.append(
            f"{row['case']}\t{row['vision_model']}\t{row['report_model']}\t"
            f"{'OK' if row['locate_pass'] else 'X'}\t{row['observe_recall']:.2f}\t"
            f"{len(row['report_violations'])}\t{row['seconds']}\t${row['cost']:.4f}"
        )
    return "\n".join(lines)
```

`src/dashpi/cli.py`에 하위 명령 추가:

```python
from tempfile import TemporaryDirectory
from dashpi.ai_client import ChatClient, load_ai_config
from dashpi.evaluation import fetch_prices, load_cases, max_cost, run as run_evaluation, summary_table

    evaluate = subcommands.add_parser("eval")
    evaluate.add_argument("--cases", type=Path, required=True)
    evaluate.add_argument("--vision-model", action="append", required=True)
    evaluate.add_argument("--report-model", action="append", required=True)
    evaluate.add_argument("--out", type=Path, required=True)
    evaluate.add_argument("--yes", action="store_true")


def run_eval(args) -> None:
    cases = load_cases(args.cases)
    if not cases:
        raise SystemExit(f"사례가 없습니다: {args.cases}")
    config = load_ai_config()
    prices = fetch_prices(sorted(set(args.vision_model + args.report_model)))
    ceiling = max_cost(len(cases), args.vision_model, args.report_model, prices)
    print(f"사례 {len(cases)}건 × 비전 {len(args.vision_model)} × 요약 {len(args.report_model)} · 예상 최대 비용 ${ceiling:.2f}")
    if not args.yes and input("계속할까요? [y/N] ").strip().lower() != "y":
        raise SystemExit(1)
    with TemporaryDirectory(prefix="dashpi-eval-") as work:
        rows = run_evaluation(cases, args.vision_model, args.report_model,
                              ChatClient(config.base_url, config.api_key), prices, args.out, Path(work))
    print(summary_table(rows))
```

`main()` 맨 앞에서 `if args.command == "eval": return run_eval(args)`.

`eval/README.md` — 사례 폴더 형식(`clip.mp4`는 커밋 금지, `expected.json` 예시 포함), 실행 예시(`dashpi eval --cases eval/cases --vision-model x-ai/grok-4.7 --vision-model openai/gpt-6-sol --vision-model anthropic/claude-sonnet-5 --report-model x-ai/grok-4.20 --report-model openai/gpt-6-luna --report-model anthropic/claude-haiku-4.5 --out eval/results/2026-09-25.jsonl`)을 적는다. 내부 문서이므로 모델 이름을 적어도 된다.

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=src QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dashpi/evaluation.py src/dashpi/cli.py tests/test_evaluation.py eval
git commit -m "feat: add dashpi eval harness for comparing analysis models"
```

---

### Task 12: 문서와 예시 파일

**Files:**
- Create: `ai.env.example`
- Modify: `.gitignore`, `README.md`, `docs/AGENT_HANDOFF.md`

- [ ] **Step 1: 예시·무시 파일**

`ai.env.example`:

```bash
# Copy to ~/.config/dashpi/ai.env and run: chmod 600 ~/.config/dashpi/ai.env
DASHPI_AI_API_KEY=
DASHPI_AI_BASE_URL=https://openrouter.ai/api/v1
DASHPI_AI_DAILY_LIMIT=20
```

`.gitignore`에 추가:

```
ai.env
eval/cases/*/clip.mp4
eval/results/
```

- [ ] **Step 2: README** — 제공사 이름 없이 수정한다.
- "요구사항"의 `Ollama 및 vision-capable model` → `AI 분석 API 키 (`ai.env.example`을 ~/.config/dashpi/ai.env로 복사)`.
- `brew install ffmpeg ollama` → `brew install ffmpeg`.
- "사고 처리 시뮬레이션"의 `ollama pull …`와 `--ollama-model qwen2.5vl:3b` 줄을 삭제하고, 키 없이 해 보는 예시 `dashpi simulate input.mp4 --trigger-seconds 30 --data-root ./demo-data --ai-model fake`를 추가한다.
- 아키텍처 다이어그램의 `Hash --> Ollama["Local Ollama Vision"]` / `Ollama --> Report` → `Hash --> AI["AI 분석 (시점 탐지·장면 관찰·요약)"]` / `AI --> Report`.
- 상태 다이어그램에 `analyzing --> awaiting_analysis: 인터넷 없음·일시 오류` / `awaiting_analysis --> analyzing: 연결 후 자동 재시도` 두 줄 추가.
- 사고 처리 흐름 4번 문장 "12개 프레임과 clip 기준 timestamp를 로컬 Ollama에 전달해" → "12개 프레임과 clip 기준 timestamp로 사고 시점을 찾고, 그 전후를 더 촘촘히 관찰해".
- "구현 및 자동 검증 완료"의 "로컬 Ollama model 확인·분석 요청·출력 schema 검증" → "AI 분석 요청·출력 schema 검증, 인터넷이 없을 때 분석 대기와 자동 재시도, 하루 분석 한도".
- "Raspberry Pi 5 네이티브 앱" 절의 설치 명령 뒤에 `mkdir -p ~/.config/dashpi && cp ai.env.example ~/.config/dashpi/ai.env && chmod 600 ~/.config/dashpi/ai.env`를 추가하고, "모델은 Pi RAM에 맞는 vision-capable Ollama 모델을 설치하고…" 문장을 "AI 분석은 외부 API로 수행하므로 Pi RAM은 녹화·영상 처리·객체 추적에 사용합니다. 인터넷이 없으면 사고는 '분석 대기'로 남고 연결되면 자동 분석됩니다."로 바꾼다.
- 저장 구조 트리에 `├── ai-usage.json`과 `├── logs/`를 추가한다.
- 확인: `grep -n -i "ollama\|openrouter\|openai\|grok\|xai" README.md` 결과가 비어야 한다.

- [ ] **Step 3: AGENT_HANDOFF** — "현재 구현 상태" 절의 분석 설명에 `AI 분석 백엔드: [OpenRouter 분석 설계](superpowers/specs/2026-09-25-openrouter-ai-analysis-design.md)` 링크 한 줄을 추가한다.

- [ ] **Step 4: 전체 테스트**

Run: `PYTHONPATH=src QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai.env.example .gitignore README.md docs/AGENT_HANDOFF.md
git commit -m "docs: document AI key setup, awaiting analysis and offline fake model"
```

---

### Task 13: Pi 배포와 수락 시험

**Files:** 없음 (운영 작업). 결과는 `docs/AGENT_HANDOFF.md`의 검증 기록에 한 단락으로 남긴다.

- [ ] **Step 1: 코드 반영** — 브랜치를 PR로 `main`에 머지한 뒤 Pi에서:

```bash
ssh wonmaker 'cd ~/DashPi-native && git pull --ff-only && git log --oneline -1'
```

- [ ] **Step 2: 키 설치 (준형이 직접)** — Pi 전용 키(`dashpi-pi`, 한도 $5)를 만든 뒤:

```bash
ssh wonmaker 'mkdir -p ~/.config/dashpi && cp ~/DashPi-native/ai.env.example ~/.config/dashpi/ai.env && chmod 600 ~/.config/dashpi/ai.env && nano ~/.config/dashpi/ai.env'
```

- [ ] **Step 3: 앱 재시작과 설정 확인** — 녹화 중이 아닌지 확인하고 DashPi를 재시작한다. 설정 화면에서 "API 키: 설정됨", 비전 `x-ai/grok-4.7`, 요약 `x-ai/grok-4.20`을 확인한다.

- [ ] **Step 4: 온라인 수락 시험** — 주행 녹화 → 30초 이상 후 사고 분석 → 종료 → 15초 후 자동 종료 → 녹화기록에서 사고가 "분석 완료"가 될 때까지 대기 → 상세에서 리포트 확인 → 리포트 QR 전송 화면 확인. `~/.local/share/dashpi/logs/dashpi.log`에서 역할별 소요 시간·토큰을 확인한다.

- [ ] **Step 5: 오프라인 수락 시험** — Pi Wi-Fi를 끈다(`nmcli radio wifi off`; Tailscale SSH가 끊기므로 Pi 화면에서 진행하거나 30분 뒤 자동 복구되는 `sudo systemd-run --on-active=30m nmcli radio wifi on`을 먼저 건다). 같은 흐름으로 사고를 만들고 "분석 대기 · 인터넷 연결 없음"을 확인한 뒤 Wi-Fi를 켜고, 사람 조작 없이 2분 안에 "분석 완료"가 되는지 확인한다.

- [ ] **Step 6: 자원 확인과 Ollama 정리** — 분석 중 `free -h`로 Ollama 방식보다 메모리 여유가 큰지 기록한다. 두 시험이 통과하면 `sudo systemctl disable --now ollama`로 Ollama를 중지한다(삭제는 별도 결정).

- [ ] **Step 7: 기록 커밋**

```bash
git add docs/AGENT_HANDOFF.md
git commit -m "docs: record Pi acceptance of AI analysis and awaiting retry"
```
