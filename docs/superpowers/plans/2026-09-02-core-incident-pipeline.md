# Core Incident Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a desktop-verifiable offline pipeline that turns deterministic video segments and a trigger into an integrity-checked incident clip and local JSON/HTML report.

**Architecture:** One Python package owns immutable incident metadata, atomic storage, time-window selection, FFmpeg clip creation, frame sampling, and a local Ollama client. Tests inject sample segments and a deterministic analyzer callable; production code reaches Ollama only through its localhost HTTP endpoint.

**Tech Stack:** Python 3.11+, standard library, FFmpeg/ffprobe, pytest; Ollama HTTP API for optional live analysis

## Global Constraints

- Runtime must work with outbound internet unavailable.
- Default recording segments are 2 seconds; incident windows are 30 seconds before and 15 seconds after the trigger.
- Material files use `.partial` → flush/fsync → SHA-256 → atomic rename → metadata update order.
- AI failure must preserve and expose the valid clip as `analysis_failed`.
- Completed incident clips are never automatically deleted in the MVP.
- The configured Ollama model is validated at startup; tests never require a live model.
- Do not add camera, hotspot, browser, QR, cloud, account, or native-app code in this plan.

---

## File Map

- `pyproject.toml` — package metadata, pytest configuration, and Python dependency floor
- `src/dashpi/config.py` — validated runtime settings
- `src/dashpi/models.py` — segment, artifact, incident state, and incident metadata types
- `src/dashpi/storage.py` — atomic file writes, hashes, metadata repository, and pure retention selection
- `src/dashpi/incidents.py` — incident window selection and overlapping-trigger behavior
- `src/dashpi/media.py` — FFmpeg clip creation, ffprobe duration, and frame sampling
- `src/dashpi/reports.py` — Ollama request, report validation, and safe HTML rendering
- `src/dashpi/pipeline.py` — state transitions that compose the modules above
- `src/dashpi/cli.py` — desktop sample-video command
- `tests/` — one focused test module per production module plus one end-to-end test

### Task 1: Package Foundation and Domain Types

**Files:**
- Create: `pyproject.toml`
- Create: `src/dashpi/__init__.py`
- Create: `src/dashpi/config.py`
- Create: `src/dashpi/models.py`
- Test: `tests/test_config.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces: `Settings`, `Segment`, `FileArtifact`, `IncidentState`, `IncidentMetadata`
- Consumes: only Python standard-library types

- [ ] **Step 1: Write failing configuration and state tests**

```python
# tests/test_config.py
from pathlib import Path
import pytest
from dashpi.config import Settings

def test_settings_use_approved_defaults(tmp_path: Path):
    settings = Settings(data_root=tmp_path, ollama_model="moondream")
    assert (settings.segment_seconds, settings.pre_seconds, settings.post_seconds) == (2.0, 30.0, 15.0)
    assert settings.frame_sample_count == 12

def test_model_name_is_required(tmp_path: Path):
    with pytest.raises(ValueError, match="ollama_model"):
        Settings(data_root=tmp_path, ollama_model="")
```

```python
# tests/test_models.py
from dashpi.models import IncidentMetadata, IncidentState

def test_new_incident_starts_collecting():
    incident = IncidentMetadata.new("inc-1", wall_time="2026-09-02T00:00:00Z", trigger_mono=40.0, post_seconds=15.0)
    assert incident.state is IncidentState.COLLECTING_POST_TRIGGER
    assert incident.post_deadline_mono == 55.0
    assert incident.transitions == [{"state": "collecting_post_trigger", "at": "2026-09-02T00:00:00Z"}]
```

- [ ] **Step 2: Run the tests and verify import failure**

Run: `python3 -m pytest tests/test_config.py tests/test_models.py -q`

Expected: FAIL because the `dashpi` package does not exist.

- [ ] **Step 3: Add the minimal package and exact types**

```toml
# pyproject.toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "dashpi"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=8,<9"]

[project.scripts]
dashpi = "dashpi.cli:main"

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

```python
# src/dashpi/config.py
from dataclasses import dataclass
from pathlib import Path

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

    def __post_init__(self) -> None:
        if not self.ollama_model.strip():
            raise ValueError("ollama_model is required")
        if min(self.segment_seconds, self.pre_seconds, self.post_seconds) <= 0:
            raise ValueError("recording durations must be positive")
```

```python
# src/dashpi/models.py
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path

class IncidentState(StrEnum):
    COLLECTING_POST_TRIGGER = "collecting_post_trigger"
    CLIPPING = "clipping"
    ANALYZING = "analyzing"
    READY = "ready"
    CLIP_FAILED = "clip_failed"
    ANALYSIS_FAILED = "analysis_failed"

@dataclass(frozen=True)
class Segment:
    path: Path
    start_mono: float
    end_mono: float

@dataclass(frozen=True)
class FileArtifact:
    path: Path
    byte_length: int
    sha256: str

@dataclass
class IncidentMetadata:
    incident_id: str
    triggered_at: str
    trigger_mono: float
    post_deadline_mono: float
    state: IncidentState
    failure_reason: str | None = None
    clip: FileArtifact | None = None
    report_json: FileArtifact | None = None
    report_html: FileArtifact | None = None
    transitions: list[dict[str, str]] = field(default_factory=list)

    @classmethod
    def new(cls, incident_id: str, wall_time: str, trigger_mono: float, post_seconds: float) -> "IncidentMetadata":
        item = cls(incident_id, wall_time, trigger_mono, trigger_mono + post_seconds, IncidentState.COLLECTING_POST_TRIGGER)
        item.transitions.append({"state": item.state.value, "at": wall_time})
        return item

    def transition(self, state: IncidentState, at: str, failure_reason: str | None = None) -> None:
        self.state, self.failure_reason = state, failure_reason
        self.transitions.append({"state": state.value, "at": at})

    def to_dict(self) -> dict:
        return asdict(self)
```

- [ ] **Step 4: Run the focused tests**

Run: `python3 -m pytest tests/test_config.py tests/test_models.py -q`

Expected: `3 passed`.

- [ ] **Step 5: Commit the domain foundation**

```bash
git add pyproject.toml src/dashpi tests/test_config.py tests/test_models.py
git commit -m "feat: define incident domain types"
```

### Task 2: Atomic Incident Storage and Retention Selection

**Files:**
- Create: `src/dashpi/storage.py`
- Test: `tests/test_storage.py`

**Interfaces:**
- Consumes: `IncidentMetadata`, `Segment`
- Produces: `sha256_file(path) -> str`, `atomic_write(path, data) -> FileArtifact`, `IncidentStore`, `bytes_to_free(...) -> int`, `choose_prunable_segments(...) -> list[Segment]`

- [ ] **Step 1: Write tests for atomic completion, round-trip metadata, and protected retention**

```python
from pathlib import Path
from dashpi.models import IncidentMetadata, Segment
from dashpi.storage import IncidentStore, atomic_write, bytes_to_free, choose_prunable_segments

def test_atomic_write_leaves_only_complete_file(tmp_path: Path):
    artifact = atomic_write(tmp_path / "report.json", b'{"ok":true}')
    assert artifact.path.read_bytes() == b'{"ok":true}'
    assert artifact.sha256 == "4062edaf750fb8074e7e83e0c9028c94e32468a8b6f1614774328ef045150f93"
    assert not (tmp_path / "report.json.partial").exists()

def test_store_round_trips_incident(tmp_path: Path):
    store = IncidentStore(tmp_path)
    store.save(IncidentMetadata.new("inc-1", "2026-09-02T00:00:00Z", 40.0, 15.0))
    assert store.load("inc-1").incident_id == "inc-1"

def test_retention_skips_protected_segments(tmp_path: Path):
    segments = [Segment(tmp_path / f"{n}.mp4", n, n + 2) for n in (0, 2, 4)]
    assert choose_prunable_segments(segments, {segments[0].path}, bytes_to_free=2, sizes={s.path: 2 for s in segments}) == [segments[1]]

def test_pressure_enforces_raw_and_free_space_limits():
    assert bytes_to_free(total=1000, used=950, raw_bytes=800, raw_max_fraction=.70, min_free_fraction=.10) == 100

def test_cleanup_removes_only_unreferenced_partials(tmp_path: Path):
    store = IncidentStore(tmp_path); active = tmp_path / "active.partial"; stale = tmp_path / "stale.partial"
    active.write_bytes(b"a"); stale.write_bytes(b"s")
    assert store.cleanup_stale_partials({active}) == [stale]
    assert active.exists() and not stale.exists()
```

- [ ] **Step 2: Run the storage tests and verify failure**

Run: `python3 -m pytest tests/test_storage.py -q`

Expected: FAIL because `dashpi.storage` does not exist.

- [ ] **Step 3: Implement only the tested storage behavior**

```python
# src/dashpi/storage.py
import hashlib, json, os
from pathlib import Path
from dashpi.models import FileArtifact, IncidentMetadata, IncidentState, Segment

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def atomic_write(path: Path, data: bytes) -> FileArtifact:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    with partial.open("wb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    digest, byte_length = sha256_file(partial), partial.stat().st_size
    partial.replace(path)
    return FileArtifact(path, byte_length, digest)

class IncidentStore:
    def __init__(self, root: Path): self.root = root
    def directory(self, incident_id: str) -> Path:
        if not incident_id or len(incident_id) > 64 or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for character in incident_id):
            raise KeyError("invalid incident id")
        return self.root / "incidents" / incident_id
    def save(self, item: IncidentMetadata) -> None:
        atomic_write(self.directory(item.incident_id) / "metadata.json", json.dumps(item.to_dict(), default=str, sort_keys=True).encode())
    def load(self, incident_id: str) -> IncidentMetadata:
        raw = json.loads((self.directory(incident_id) / "metadata.json").read_text())
        raw["state"] = IncidentState(raw["state"])
        for key in ("clip", "report_json", "report_html"):
            if raw.get(key): raw[key] = FileArtifact(Path(raw[key]["path"]), raw[key]["byte_length"], raw[key]["sha256"])
        return IncidentMetadata(**raw)
    def cleanup_stale_partials(self, active: set[Path]) -> list[Path]:
        removed = []
        for path in self.root.rglob("*.partial"):
            if path in active: continue
            path.unlink(); removed.append(path)
        return removed

def bytes_to_free(total: int, used: int, raw_bytes: int, raw_max_fraction: float, min_free_fraction: float) -> int:
    raw_excess = raw_bytes - int(total * raw_max_fraction)
    free_shortfall = int(total * min_free_fraction) - (total - used)
    return max(0, raw_excess, free_shortfall)

def choose_prunable_segments(segments: list[Segment], protected: set[Path], bytes_to_free: int, sizes: dict[Path, int]) -> list[Segment]:
    chosen, freed = [], 0
    for segment in sorted(segments, key=lambda value: value.start_mono):
        if segment.path in protected: continue
        chosen.append(segment); freed += sizes[segment.path]
        if freed >= bytes_to_free: break
    return chosen
```

- [ ] **Step 4: Run storage tests and the existing suite**

Run: `python3 -m pytest tests/test_storage.py -q && python3 -m pytest -q`

Expected: storage tests pass; the full suite remains green.

- [ ] **Step 5: Commit atomic storage**

```bash
git add src/dashpi/storage.py tests/test_storage.py
git commit -m "feat: persist incident files atomically"
```

### Task 3: Incident Windows and Overlapping Triggers

**Files:**
- Create: `src/dashpi/incidents.py`
- Test: `tests/test_incidents.py`

**Interfaces:**
- Consumes: `Settings`, `Segment`, `IncidentMetadata`
- Produces: `segments_for_window(...)`, `IncidentCoordinator.trigger(...)`, `IncidentCoordinator.ready_at(now) -> list[IncidentMetadata]`

- [ ] **Step 1: Write boundary and overlap tests**

```python
from pathlib import Path
from dashpi.config import Settings
from dashpi.incidents import IncidentCoordinator, segments_for_window
from dashpi.models import Segment

def test_window_selects_every_overlapping_segment(tmp_path: Path):
    segments = [Segment(tmp_path / f"{n}.mp4", n, n + 2) for n in range(0, 60, 2)]
    selected = segments_for_window(segments, start=10.0, end=25.0)
    assert (selected[0].start_mono, selected[-1].end_mono) == (10, 26)

def test_overlapping_trigger_extends_existing_incident(tmp_path: Path):
    coordinator = IncidentCoordinator(Settings(tmp_path, "moondream"), id_factory=iter(["inc-1", "inc-2"]).__next__)
    first = coordinator.trigger(40.0, "2026-09-02T00:00:00Z")
    second = coordinator.trigger(50.0, "2026-09-02T00:00:10Z")
    assert second.incident_id == first.incident_id
    assert second.post_deadline_mono == 65.0
```

- [ ] **Step 2: Run and verify missing implementation**

Run: `python3 -m pytest tests/test_incidents.py -q`

Expected: FAIL because `dashpi.incidents` does not exist.

- [ ] **Step 3: Implement interval overlap and deadline extension**

```python
# src/dashpi/incidents.py
from collections.abc import Callable
from dashpi.config import Settings
from dashpi.models import IncidentMetadata, IncidentState, Segment

def segments_for_window(segments: list[Segment], start: float, end: float) -> list[Segment]:
    return [segment for segment in segments if segment.start_mono < end and segment.end_mono > start]

class IncidentCoordinator:
    def __init__(self, settings: Settings, id_factory: Callable[[], str]):
        self.settings, self.id_factory, self.active = settings, id_factory, []

    def trigger(self, trigger_mono: float, wall_time: str) -> IncidentMetadata:
        requested_start = trigger_mono - self.settings.pre_seconds
        requested_end = trigger_mono + self.settings.post_seconds
        for incident in self.active:
            existing_start = incident.trigger_mono - self.settings.pre_seconds
            if existing_start < requested_end and incident.post_deadline_mono > requested_start:
                incident.post_deadline_mono = max(incident.post_deadline_mono, requested_end)
                return incident
        incident = IncidentMetadata.new(self.id_factory(), wall_time, trigger_mono, self.settings.post_seconds)
        self.active.append(incident)
        return incident

    def ready_at(self, now: float) -> list[IncidentMetadata]:
        return [item for item in self.active if item.state is IncidentState.COLLECTING_POST_TRIGGER and item.post_deadline_mono <= now]
```

- [ ] **Step 4: Run incident tests and full suite**

Run: `python3 -m pytest tests/test_incidents.py -q && python3 -m pytest -q`

Expected: all tests pass.

- [ ] **Step 5: Commit trigger behavior**

```bash
git add src/dashpi/incidents.py tests/test_incidents.py
git commit -m "feat: coordinate incident trigger windows"
```

### Task 4: FFmpeg Clip Creation and Frame Sampling

**Files:**
- Create: `src/dashpi/media.py`
- Create: `tests/media_factory.py`
- Test: `tests/test_media.py`

**Interfaces:**
- Consumes: ordered `list[Segment]`, target path, window start/duration
- Produces: `segment_source(...) -> list[Segment]`, `build_clip(...) -> FileArtifact`, `probe_duration(path) -> float`, `sample_frames(...) -> list[Path]`

- [ ] **Step 1: Generate deterministic media and write failing behavior tests**

```python
# tests/media_factory.py
import subprocess
from pathlib import Path

def make_video(path: Path, seconds: int, color: str = "blue") -> Path:
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"color={color}:s=320x240:r=10:d={seconds}", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)
    return path
```

```python
# tests/test_media.py
from dashpi.media import build_clip, probe_duration, sample_frames
from dashpi.models import Segment
from tests.media_factory import make_video

def test_clip_and_twelve_samples(tmp_path):
    paths = [make_video(tmp_path / f"{n}.mp4", 2) for n in range(3)]
    segments = [Segment(path, n * 2.0, n * 2.0 + 2.0) for n, path in enumerate(paths)]
    artifact = build_clip(segments, tmp_path / "clip.mp4", window_start=0.0, duration=6.0)
    assert 5.8 <= probe_duration(artifact.path) <= 6.2
    assert len(sample_frames(artifact.path, tmp_path / "frames", 12)) == 12
```

- [ ] **Step 2: Run the media test and verify failure**

Run: `python3 -m pytest tests/test_media.py -q`

Expected: FAIL because `dashpi.media` does not exist; if `ffmpeg` is absent, stop and install it before implementation.

- [ ] **Step 3: Implement FFmpeg through argument arrays, never shell strings**

```python
# src/dashpi/media.py
import json, os, subprocess
from pathlib import Path
from dashpi.models import FileArtifact, Segment
from dashpi.storage import sha256_file

def probe_duration(path: Path) -> float:
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)], check=True, capture_output=True, text=True)
    return float(json.loads(result.stdout)["format"]["duration"])

def segment_source(source: Path, output_dir: Path, segment_seconds: float) -> list[Segment]:
    output_dir.mkdir(parents=True, exist_ok=True)
    pattern = output_dir / "%06d.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(source), "-map", "0:v:0", "-an", "-c:v", "libx264", "-force_key_frames", f"expr:gte(t,n_forced*{segment_seconds})", "-f", "segment", "-segment_time", str(segment_seconds), "-reset_timestamps", "1", str(pattern)], check=True)
    start, segments = 0.0, []
    for path in sorted(output_dir.glob("*.mp4")):
        end = start + probe_duration(path)
        segments.append(Segment(path, start, end)); start = end
    return segments

def build_clip(segments: list[Segment], output: Path, window_start: float, duration: float) -> FileArtifact:
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(output.name + ".partial")
    manifest = output.with_suffix(".concat.txt")
    manifest.write_text("".join(f"file '{segment.path.as_posix().replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'\n" for segment in segments))
    offset = max(0.0, window_start - segments[0].start_mono)
    try:
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(manifest), "-ss", str(offset), "-t", str(duration), "-c", "copy", "-f", "mp4", str(partial)], check=True)
        with partial.open("rb") as completed: os.fsync(completed.fileno())
        digest, byte_length = sha256_file(partial), partial.stat().st_size
        partial.replace(output)
        return FileArtifact(output, byte_length, digest)
    finally:
        manifest.unlink(missing_ok=True)

def sample_frames(clip: Path, output_dir: Path, count: int) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    duration = probe_duration(clip)
    paths = []
    for index in range(count):
        target = output_dir / f"{index:02d}.jpg"
        timestamp = duration * (index + 0.5) / count
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", str(timestamp), "-i", str(clip), "-frames:v", "1", str(target)], check=True)
        paths.append(target)
    return paths
```

- [ ] **Step 4: Run media and full tests**

Run: `python3 -m pytest tests/test_media.py -q && python3 -m pytest -q`

Expected: clip duration assertion and 12-frame assertion pass.

- [ ] **Step 5: Commit media processing**

```bash
git add src/dashpi/media.py tests/media_factory.py tests/test_media.py
git commit -m "feat: build incident clips with ffmpeg"
```

### Task 5: Local Ollama Reports with Safe Failure

**Files:**
- Create: `src/dashpi/reports.py`
- Test: `tests/test_reports.py`

**Interfaces:**
- Produces: `OllamaClient.validate_model() -> None`, `OllamaClient.analyze(frames) -> dict`, `validate_report(raw, clip_sha256, model, generated_at) -> dict`, `render_report_html(report) -> str`
- Consumes: sampled JPEG paths and the configured model name

- [ ] **Step 1: Write report validation and escaping tests**

```python
import pytest
from dashpi.reports import OllamaClient, render_report_html, validate_report

def test_report_binds_model_and_source_digest():
    report = validate_report({"summary": "Vehicle stopped", "observations": [{"timestamp": 2.5, "description": "Brake lights"}], "limitations": ["Single camera"]}, "abc", "moondream", "2026-09-02T00:00:00Z")
    assert report["source_clip_sha256"] == "abc"
    assert report["model"] == "moondream"

def test_html_escapes_model_output():
    html = render_report_html({"summary": "<script>alert(1)</script>", "observations": [], "limitations": [], "source_clip_sha256": "abc", "model": "m", "generated_at": "now"})
    assert "<script>" not in html
    assert "&lt;script&gt;" in html

def test_report_rejects_malformed_observation():
    with pytest.raises(ValueError, match="observation"):
        validate_report({"summary":"x","observations":[{"timestamp":"soon","description":3}],"limitations":[]}, "abc", "m", "now")

def test_missing_configured_model_fails_startup(monkeypatch):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): return None
        def read(self): return b'{"models":[{"name":"other"}]}'
    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: Response())
    with pytest.raises(ValueError, match="not installed"):
        OllamaClient("moondream").validate_model()
```

- [ ] **Step 2: Run and verify missing report module**

Run: `python3 -m pytest tests/test_reports.py -q`

Expected: FAIL because `dashpi.reports` does not exist.

- [ ] **Step 3: Implement localhost Ollama request, strict shape validation, and escaped HTML**

```python
# src/dashpi/reports.py
import base64, html, json, urllib.request
from pathlib import Path

class OllamaClient:
    def __init__(self, model: str, base_url: str = "http://127.0.0.1:11434", timeout: float = 120.0):
        self.model, self.base_url, self.timeout = model, base_url.rstrip("/"), timeout
    def validate_model(self) -> None:
        with urllib.request.urlopen(self.base_url + "/api/tags", timeout=5.0) as response:
            names = {item["name"] for item in json.loads(response.read())["models"]}
        if self.model not in names: raise ValueError(f"Ollama model not installed: {self.model}")
    def analyze(self, frames: list[Path]) -> dict:
        images = [base64.b64encode(path.read_bytes()).decode() for path in frames]
        body = json.dumps({"model": self.model, "stream": False, "format": "json", "prompt": "Describe visible events by timestamp. Return summary, observations, limitations.", "images": images}).encode()
        request = urllib.request.Request(self.base_url + "/api/generate", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(json.loads(response.read())["response"])

def validate_report(raw: dict, clip_sha256: str, model: str, generated_at: str) -> dict:
    if not isinstance(raw.get("summary"), str) or not isinstance(raw.get("observations"), list) or not isinstance(raw.get("limitations"), list):
        raise ValueError("invalid report shape")
    if any(not isinstance(item, dict) or not isinstance(item.get("timestamp"), (int, float)) or not isinstance(item.get("description"), str) for item in raw["observations"]):
        raise ValueError("invalid observation")
    if any(not isinstance(item, str) for item in raw["limitations"]): raise ValueError("invalid limitation")
    return {**raw, "source_clip_sha256": clip_sha256, "model": model, "generated_at": generated_at}

def render_report_html(report: dict) -> str:
    observations = "".join(f"<li>{float(item['timestamp']):.1f}s — {html.escape(str(item['description']))}</li>" for item in report["observations"])
    limitations = "".join(f"<li>{html.escape(str(item))}</li>" for item in report["limitations"])
    return f"<main><h1>DashPi incident report</h1><p>{html.escape(report['summary'])}</p><h2>Observations</h2><ul>{observations}</ul><h2>Limitations</h2><ul>{limitations}</ul></main>"
```

- [ ] **Step 4: Run report and full tests**

Run: `python3 -m pytest tests/test_reports.py -q && python3 -m pytest -q`

Expected: all tests pass without contacting Ollama.

- [ ] **Step 5: Commit local report generation**

```bash
git add src/dashpi/reports.py tests/test_reports.py
git commit -m "feat: generate local incident reports"
```

### Task 6: Pipeline Orchestration and Offline End-to-End Check

**Files:**
- Create: `src/dashpi/pipeline.py`
- Create: `src/dashpi/cli.py`
- Test: `tests/test_pipeline.py`
- Test: `tests/test_offline_e2e.py`

**Interfaces:**
- Consumes: `Settings`, `IncidentStore`, segments, and `analyze(frames) -> dict`
- Produces: `IncidentPipeline.process(incident, segments, analyze) -> IncidentMetadata`; CLI `dashpi simulate VIDEO --trigger-seconds N`

- [ ] **Step 1: Write success and AI-failure pipeline tests**

```python
# tests/test_pipeline.py
import pytest
from dashpi.config import Settings
from dashpi.models import IncidentMetadata, Segment
from dashpi.pipeline import IncidentPipeline
from dashpi.storage import IncidentStore
from tests.media_factory import make_video

@pytest.fixture
def pipeline_fixture(tmp_path):
    paths = [make_video(tmp_path / f"{index}.mp4", 2) for index in range(3)]
    segments = [Segment(path, index * 2.0, index * 2.0 + 2.0) for index, path in enumerate(paths)]
    settings = Settings(tmp_path / "data", "test-model")
    pipeline = IncidentPipeline(settings, IncidentStore(settings.data_root))
    incident = IncidentMetadata.new("inc-1", "2026-09-02T00:00:00Z", 3.0, settings.post_seconds)
    return pipeline, incident, segments

def test_pipeline_creates_clip_and_reports(pipeline_fixture):
    pipeline, incident, segments = pipeline_fixture
    result = pipeline.process(incident, segments, lambda frames: {"summary": "Stopped", "observations": [], "limitations": []})
    assert result.state.value == "ready"
    assert result.clip.path.exists() and result.report_json.path.exists() and result.report_html.path.exists()

def test_ai_failure_preserves_clip(pipeline_fixture):
    pipeline, incident, segments = pipeline_fixture
    def fail(_frames): raise TimeoutError("model timeout")
    result = pipeline.process(incident, segments, fail)
    assert result.state.value == "analysis_failed"
    assert result.clip.path.exists()
    assert result.transitions[-1]["state"] == "analysis_failed"
```

```python
# tests/test_offline_e2e.py
import urllib.request
from tests.test_pipeline import pipeline_fixture

def test_injected_analysis_pipeline_never_opens_network(pipeline_fixture, monkeypatch):
    def blocked(*_args, **_kwargs): raise AssertionError("network attempted")
    monkeypatch.setattr(urllib.request, "urlopen", blocked)
    pipeline, incident, segments = pipeline_fixture
    result = pipeline.process(incident, segments, lambda _frames: {"summary":"Offline","observations":[],"limitations":[]})
    assert result.state.value == "ready"
```

- [ ] **Step 2: Run pipeline tests and verify failure**

Run: `python3 -m pytest tests/test_pipeline.py -q`

Expected: FAIL because `IncidentPipeline` does not exist.

- [ ] **Step 3: Implement the linear state machine and thin CLI**

```python
# src/dashpi/pipeline.py
from datetime import UTC, datetime
import json
from dashpi.media import build_clip, sample_frames
from dashpi.models import IncidentMetadata, IncidentState, Segment
from dashpi.reports import render_report_html, validate_report
from dashpi.storage import IncidentStore, atomic_write

class IncidentPipeline:
    def __init__(self, settings, store: IncidentStore): self.settings, self.store = settings, store
    def process(self, incident: IncidentMetadata, segments: list[Segment], analyze) -> IncidentMetadata:
        directory = self.store.directory(incident.incident_id)
        try:
            incident.transition(IncidentState.CLIPPING, datetime.now(UTC).isoformat()); self.store.save(incident)
            window_start = incident.trigger_mono - self.settings.pre_seconds
            incident.clip = build_clip(segments, directory / "clip.mp4", window_start, incident.post_deadline_mono - window_start)
        except Exception as error:
            incident.transition(IncidentState.CLIP_FAILED, datetime.now(UTC).isoformat(), str(error)); self.store.save(incident); return incident
        try:
            incident.transition(IncidentState.ANALYZING, datetime.now(UTC).isoformat()); self.store.save(incident)
            frames = sample_frames(incident.clip.path, directory / "frames", self.settings.frame_sample_count)
            report = validate_report(analyze(frames), incident.clip.sha256, self.settings.ollama_model, datetime.now(UTC).isoformat())
            incident.report_json = atomic_write(directory / "report.json", json.dumps(report, sort_keys=True).encode())
            incident.report_html = atomic_write(directory / "report.html", render_report_html(report).encode())
            incident.transition(IncidentState.READY, datetime.now(UTC).isoformat())
        except Exception as error:
            incident.transition(IncidentState.ANALYSIS_FAILED, datetime.now(UTC).isoformat(), str(error))
        self.store.save(incident); return incident
```

```python
# src/dashpi/cli.py
import argparse, json, uuid
from datetime import UTC, datetime
from pathlib import Path
from dashpi.config import Settings
from dashpi.media import segment_source
from dashpi.models import IncidentMetadata
from dashpi.pipeline import IncidentPipeline
from dashpi.reports import OllamaClient
from dashpi.storage import IncidentStore

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command", required=True)
    simulate = subcommands.add_parser("simulate")
    simulate.add_argument("video", type=Path)
    simulate.add_argument("--trigger-seconds", type=float, required=True)
    simulate.add_argument("--data-root", type=Path, required=True)
    simulate.add_argument("--ollama-model", required=True)
    return parser

def main() -> None:
    args = build_parser().parse_args()
    settings = Settings(args.data_root, args.ollama_model)
    segments = segment_source(args.video, settings.data_root / "raw", settings.segment_seconds)
    incident = IncidentMetadata.new(uuid.uuid4().hex, datetime.now(UTC).isoformat(), args.trigger_seconds, settings.post_seconds)
    client = OllamaClient(settings.ollama_model); client.validate_model()
    result = IncidentPipeline(settings, IncidentStore(settings.data_root)).process(incident, segments, client.analyze)
    print(json.dumps(result.to_dict(), default=str))
```

- [ ] **Step 4: Run focused, full, and offline checks**

Run: `python3 -m pytest tests/test_pipeline.py tests/test_offline_e2e.py -q`

Expected: both success and forced-model-failure flows pass with `urllib.request.urlopen` monkeypatched to raise if any network call occurs.

Run: `python3 -m pytest -q`

Expected: full suite passes.

- [ ] **Step 5: Commit the desktop core vertical slice**

```bash
git add src/dashpi/pipeline.py src/dashpi/cli.py tests/test_pipeline.py tests/test_offline_e2e.py
git commit -m "feat: complete offline incident pipeline"
```

## Plan Acceptance

Run:

```bash
python3 -m pytest -q
dashpi --help
```

Accept when the suite creates a clip and both report formats without outbound network access, the forced Ollama failure test retains the clip with `analysis_failed`, and the CLI help command exits successfully. A manual CLI analysis run requires a locally installed Ollama vision model and no internet connection.
