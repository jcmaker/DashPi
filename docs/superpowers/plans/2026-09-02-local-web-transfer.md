# Local Web Transfer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a phone on DashPi's local network list incidents, read reports, seek video, and resume integrity-checked downloads without internet or a native app.

**Architecture:** FastAPI reads only completed metadata from `IncidentStore` and serves a dependency-free static web page. A small explicit Range parser streams file slices; desktop tests bind localhost, while Raspberry Pi deployment later binds the same process to the hotspot interface.

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, HTTPX/pytest, semantic HTML, vanilla JavaScript

## Global Constraints

- Complete `2026-09-02-core-incident-pipeline.md` first.
- Runtime must work with outbound internet unavailable.
- The API exposes local incident files only; request path values never become filesystem paths.
- Only metadata states `ready` and `analysis_failed` may expose a clip.
- Video responses support single HTTP byte ranges, resume, and browser seeking.
- No cloud, account, native app, frontend framework, hotspot controller, or optical code belongs in this plan.
- Desktop bind default is `127.0.0.1`; Raspberry Pi interface binding is an explicit command-line value.

---

## File Map

- `pyproject.toml` — FastAPI/Uvicorn runtime and HTTPX test dependencies
- `src/dashpi/storage.py` — list completed incident metadata
- `src/dashpi/ranges.py` — validated single-range parsing and streaming
- `src/dashpi/api.py` — application factory and incident endpoints
- `src/dashpi/server.py` — explicit host/port command
- `src/dashpi/web/index.html` — incident list, report view, and video player
- `tests/test_ranges.py` — unit checks for valid and invalid ranges
- `tests/test_api.py` — endpoint, traversal, resume, and hash checks
- `tests/test_web.py` — static page contract and absence of remote resources

### Task 1: Incident Listing Contract

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/dashpi/storage.py`
- Create: `src/dashpi/api.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `IncidentStore.load(id)`, stored `IncidentMetadata`
- Produces: `IncidentStore.list() -> list[IncidentMetadata]`, `create_app(store) -> FastAPI`

- [ ] **Step 1: Write a failing incident-list API test**

```python
from fastapi.testclient import TestClient
from dashpi.api import create_app
from dashpi.models import IncidentMetadata, IncidentState
from dashpi.storage import IncidentStore

def test_list_returns_metadata_not_filesystem_paths(tmp_path):
    store = IncidentStore(tmp_path)
    incident = IncidentMetadata.new("inc-1", "2026-09-02T00:00:00Z", 40.0, 15.0)
    incident.state = IncidentState.ANALYSIS_FAILED
    incident.failure_reason = "model timeout"
    store.save(incident)
    response = TestClient(create_app(store)).get("/api/incidents")
    assert response.status_code == 200
    assert response.json() == [{"incident_id": "inc-1", "triggered_at": "2026-09-02T00:00:00Z", "state": "analysis_failed", "failure_reason": "model timeout", "has_clip": False, "has_report": False}]
    assert str(tmp_path) not in response.text
```

- [ ] **Step 2: Run and verify failure**

Run: `python3 -m pytest tests/test_api.py::test_list_returns_metadata_not_filesystem_paths -q`

Expected: FAIL because FastAPI and `dashpi.api` are unavailable.

- [ ] **Step 3: Add dependencies and minimal list endpoint**

```toml
# Add to pyproject.toml
[project]
dependencies = ["fastapi>=0.116,<1", "uvicorn>=0.35,<1"]

[project.optional-dependencies]
dev = ["pytest>=8,<9", "httpx>=0.28,<1"]
```

```python
# add to src/dashpi/storage.py
def list(self) -> list[IncidentMetadata]:
    parent = self.root / "incidents"
    if not parent.exists(): return []
    return sorted((self.load(path.name) for path in parent.iterdir() if (path / "metadata.json").is_file()), key=lambda item: item.triggered_at, reverse=True)
```

```python
# src/dashpi/api.py
from fastapi import FastAPI
from dashpi.storage import IncidentStore

def create_app(store: IncidentStore) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None)
    @app.get("/api/incidents")
    def list_incidents():
        return [{"incident_id": item.incident_id, "triggered_at": item.triggered_at, "state": item.state, "failure_reason": item.failure_reason, "has_clip": item.clip is not None, "has_report": item.report_html is not None} for item in store.list()]
    return app
```

- [ ] **Step 4: Run focused and full tests**

Run: `python3 -m pytest tests/test_api.py::test_list_returns_metadata_not_filesystem_paths -q && python3 -m pytest -q`

Expected: the API contract passes and the core suite stays green.

- [ ] **Step 5: Commit listing API**

```bash
git add pyproject.toml src/dashpi/storage.py src/dashpi/api.py tests/test_api.py
git commit -m "feat: list incidents over local api"
```

### Task 2: Safe Single-Range File Streaming

**Files:**
- Create: `src/dashpi/ranges.py`
- Modify: `src/dashpi/api.py`
- Modify: `tests/test_api.py`
- Test: `tests/test_ranges.py`

**Interfaces:**
- Produces: `parse_range(header, size) -> tuple[int, int] | None`, `range_response(path, header, media_type) -> Response`
- Consumes: internally resolved `Path`; never a user-supplied filename

- [ ] **Step 1: Write parser and resumed-download tests**

```python
# tests/test_ranges.py
import pytest
from dashpi.ranges import parse_range

def test_range_forms():
    assert parse_range(None, 10) is None
    assert parse_range("bytes=2-5", 10) == (2, 5)
    assert parse_range("bytes=7-", 10) == (7, 9)
    assert parse_range("bytes=-3", 10) == (7, 9)

@pytest.mark.parametrize("value", ["items=0-1", "bytes=9-2", "bytes=0-1,4-5", "bytes=20-30"])
def test_invalid_range_is_rejected(value):
    with pytest.raises(ValueError): parse_range(value, 10)
```

```python
# append to tests/test_api.py
import pytest
from dashpi.storage import atomic_write

@pytest.fixture
def client_with_ready_incident(tmp_path):
    payload = bytes(range(32))
    store = IncidentStore(tmp_path)
    incident = IncidentMetadata.new("inc-1", "2026-09-02T00:00:00Z", 40.0, 15.0)
    incident.state = IncidentState.READY
    incident.clip = atomic_write(store.directory("inc-1") / "clip.mp4", payload)
    incident.report_json = atomic_write(store.directory("inc-1") / "report.json", b'{"summary":"Stopped","observations":[],"limitations":[]}')
    incident.report_html = atomic_write(store.directory("inc-1") / "report.html", b"<h1>DashPi incident report</h1>")
    store.save(incident)
    return TestClient(create_app(store)), payload, incident.clip.sha256

def test_clip_supports_resume_and_hash(client_with_ready_incident):
    client, payload, digest = client_with_ready_incident
    response = client.get("/api/incidents/inc-1/clip", headers={"Range": "bytes=4-8"})
    assert response.status_code == 206
    assert response.content == payload[4:9]
    assert response.headers["content-range"] == f"bytes 4-8/{len(payload)}"
    assert response.headers["etag"] == f'"sha256:{digest}"'

def test_invalid_incident_id_does_not_escape_store(client_with_ready_incident):
    client, _payload, _digest = client_with_ready_incident
    assert client.get("/api/incidents/invalid!/clip").status_code == 404
```

- [ ] **Step 2: Run and verify failure**

Run: `python3 -m pytest tests/test_ranges.py tests/test_api.py::test_clip_supports_resume_and_hash -q`

Expected: FAIL because the Range parser and clip endpoint do not exist.

- [ ] **Step 3: Implement bounded streaming and the ID-only endpoint**

```python
# src/dashpi/ranges.py
from pathlib import Path
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

def parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    if header is None: return None
    if not header.startswith("bytes=") or "," in header: raise ValueError("unsupported range")
    start_text, end_text = header[6:].split("-", 1)
    if not start_text:
        length = int(end_text)
        if length <= 0: raise ValueError("invalid suffix")
        return max(0, size - length), size - 1
    start = int(start_text); end = int(end_text) if end_text else size - 1
    if start < 0 or start >= size or end < start: raise ValueError("range outside file")
    return start, min(end, size - 1)

def range_response(path: Path, header: str | None, media_type: str, digest: str):
    size = path.stat().st_size
    try: selected = parse_range(header, size)
    except (ValueError, TypeError): raise HTTPException(416, headers={"Content-Range": f"bytes */{size}"})
    start, end = selected or (0, size - 1)
    def body():
        with path.open("rb") as source:
            source.seek(start); remaining = end - start + 1
            while remaining:
                chunk = source.read(min(1024 * 1024, remaining))
                if not chunk: break
                remaining -= len(chunk); yield chunk
    headers = {"Accept-Ranges": "bytes", "Content-Length": str(end - start + 1), "ETag": f'"sha256:{digest}"'}
    if selected: headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return StreamingResponse(body(), status_code=206 if selected else 200, media_type=media_type, headers=headers)
```

```python
# add inside create_app in src/dashpi/api.py
from fastapi import Header, HTTPException
from dashpi.models import IncidentState
from dashpi.ranges import range_response

@app.get("/api/incidents/{incident_id}/clip")
def get_clip(incident_id: str, range_header: str | None = Header(None, alias="Range")):
    try: item = store.load(incident_id)
    except (FileNotFoundError, KeyError): raise HTTPException(404)
    if item.state not in {IncidentState.READY, IncidentState.ANALYSIS_FAILED} or item.clip is None: raise HTTPException(409)
    return range_response(item.clip.path, range_header, "video/mp4", item.clip.sha256)
```

- [ ] **Step 4: Run Range, API, and full suites**

Run: `python3 -m pytest tests/test_ranges.py tests/test_api.py -q && python3 -m pytest -q`

Expected: valid full/range responses pass; invalid and traversal-shaped incident IDs return 404 or 416 without exposing paths.

- [ ] **Step 5: Commit ranged transfer**

```bash
git add src/dashpi/ranges.py src/dashpi/api.py tests/test_ranges.py tests/test_api.py
git commit -m "feat: stream incident clips with range support"
```

### Task 3: Report Endpoint and Dependency-Free Local UI

**Files:**
- Create: `src/dashpi/web/index.html`
- Modify: `src/dashpi/api.py`
- Modify: `tests/test_api.py`
- Create: `tests/test_web.py`

**Interfaces:**
- Produces: `GET /`, `GET /api/incidents/{id}`, `GET /api/incidents/{id}/report.html`
- Consumes: incident list JSON and same-origin report/clip URLs

- [ ] **Step 1: Write failing report and offline-asset tests**

```python
def test_report_is_same_origin_html(client_with_ready_incident):
    client, _payload, _digest = client_with_ready_incident
    response = client.get("/api/incidents/inc-1/report.html")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "DashPi incident report" in response.text

def test_incident_detail_returns_report_without_paths(client_with_ready_incident):
    client, _payload, _digest = client_with_ready_incident
    response = client.get("/api/incidents/inc-1")
    assert response.json()["report"]["summary"] == "Stopped"
    assert "report.html" not in response.text and "clip.mp4" not in response.text
```

```python
# tests/test_web.py
from pathlib import Path

def test_local_ui_has_no_remote_assets():
    html = Path("src/dashpi/web/index.html").read_text()
    assert "https://" not in html and "http://" not in html
    assert "fetch('/api/incidents')" in html
    assert '<video controls' in html
```

- [ ] **Step 2: Run and verify missing endpoints/assets**

Run: `python3 -m pytest tests/test_api.py::test_report_is_same_origin_html tests/test_web.py -q`

Expected: FAIL because the report endpoint and page do not exist.

- [ ] **Step 3: Add safe report serving and the smallest useful page**

```python
# add inside create_app in src/dashpi/api.py
import json
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

@app.get("/api/incidents/{incident_id}/report.html")
def get_report(incident_id: str):
    try: item = store.load(incident_id)
    except (FileNotFoundError, KeyError): raise HTTPException(404)
    if item.report_html is None: raise HTTPException(404)
    return FileResponse(item.report_html.path, media_type="text/html", headers={"ETag": f'"sha256:{item.report_html.sha256}"'})

@app.get("/api/incidents/{incident_id}")
def get_incident(incident_id: str):
    try: item = store.load(incident_id)
    except (FileNotFoundError, KeyError): raise HTTPException(404)
    report = json.loads(item.report_json.path.read_text()) if item.report_json else None
    return {"incident_id": item.incident_id, "triggered_at": item.triggered_at, "state": item.state, "failure_reason": item.failure_reason, "report": report}

app.mount("/", StaticFiles(directory=Path(__file__).parent / "web", html=True), name="web")
```

```html
<!-- src/dashpi/web/index.html -->
<main>
  <h1>DashPi incidents</h1>
  <p id="status" role="status">Loading…</p>
  <ul id="incidents"></ul>
  <section id="detail" hidden>
    <iframe id="report" title="Incident report"></iframe>
    <video controls preload="metadata"></video>
  </section>
</main>
<script>
const status = document.querySelector('#status');
const list = document.querySelector('#incidents');
const detail = document.querySelector('#detail');
const report = document.querySelector('#report');
const video = document.querySelector('video');
fetch('/api/incidents').then(r => r.json()).then(items => {
  status.textContent = items.length ? `${items.length} incident(s)` : 'No incidents';
  items.forEach(item => {
    const button = document.createElement('button');
    button.textContent = `${item.triggered_at} — ${item.state}`;
    button.onclick = () => {
      detail.hidden = false;
      report.src = `/api/incidents/${encodeURIComponent(item.incident_id)}/report.html`;
      video.src = `/api/incidents/${encodeURIComponent(item.incident_id)}/clip`;
    };
    const row = document.createElement('li'); row.append(button); list.append(row);
  });
}).catch(() => { status.textContent = 'Unable to load incidents'; });
</script>
```

- [ ] **Step 4: Run API/web tests**

Run: `python3 -m pytest tests/test_api.py tests/test_web.py -q && python3 -m pytest -q`

Expected: all tests pass.

- [ ] **Step 5: Commit the local UI**

```bash
git add src/dashpi/web/index.html src/dashpi/api.py tests/test_api.py tests/test_web.py
git commit -m "feat: add local incident viewer"
```

### Task 4: Explicit Server Command and Offline Integration

**Files:**
- Create: `src/dashpi/server.py`
- Modify: `pyproject.toml`
- Test: `tests/test_server.py`
- Test: `tests/test_local_web_e2e.py`

**Interfaces:**
- Produces: `dashpi-server --data-root PATH --host HOST --port PORT`
- Consumes: existing `IncidentStore` and `create_app(store)`

- [ ] **Step 1: Write argument and offline integration tests**

```python
from dashpi.server import build_parser

def test_server_defaults_to_loopback():
    args = build_parser().parse_args(["--data-root", "/tmp/dashpi"])
    assert (args.host, args.port) == ("127.0.0.1", 8000)
```

```python
# tests/test_local_web_e2e.py
import hashlib, socket
from fastapi.testclient import TestClient
from dashpi.api import create_app
from dashpi.models import IncidentMetadata, IncidentState
from dashpi.storage import IncidentStore, atomic_write

def test_local_routes_rebuild_clip_without_outbound_network(tmp_path, monkeypatch):
    def blocked(*_args, **_kwargs): raise AssertionError("outbound network attempted")
    monkeypatch.setattr(socket, "create_connection", blocked)
    payload = bytes(range(256)) * 8
    store = IncidentStore(tmp_path)
    item = IncidentMetadata.new("inc-1", "2026-09-02T00:00:00Z", 40.0, 15.0)
    item.state = IncidentState.READY
    item.clip = atomic_write(store.directory("inc-1") / "clip.mp4", payload)
    item.report_html = atomic_write(store.directory("inc-1") / "report.html", b"<h1>DashPi incident report</h1>")
    store.save(item); client = TestClient(create_app(store))
    assert client.get("/").status_code == 200
    assert client.get("/api/incidents").json()[0]["incident_id"] == "inc-1"
    first = client.get("/api/incidents/inc-1/clip", headers={"Range": "bytes=0-1023"}).content
    second = client.get("/api/incidents/inc-1/clip", headers={"Range": "bytes=1024-"}).content
    assert hashlib.sha256(first + second).hexdigest() == item.clip.sha256
```

- [ ] **Step 2: Run and verify missing server module**

Run: `python3 -m pytest tests/test_server.py tests/test_local_web_e2e.py -q`

Expected: FAIL because `dashpi.server` does not exist.

- [ ] **Step 3: Implement the explicit server entry point**

```python
# src/dashpi/server.py
import argparse
from pathlib import Path
import uvicorn
from dashpi.api import create_app
from dashpi.storage import IncidentStore

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser

def main() -> None:
    args = build_parser().parse_args()
    uvicorn.run(create_app(IncidentStore(args.data_root)), host=args.host, port=args.port)
```

```toml
# add to [project.scripts] in pyproject.toml
dashpi-server = "dashpi.server:main"
```

- [ ] **Step 4: Run fresh verification**

Run: `python3 -m pytest tests/test_server.py tests/test_local_web_e2e.py -q && python3 -m pytest -q`

Expected: integration rebuilds the original clip byte-for-byte and the full suite passes.

- [ ] **Step 5: Commit the local transfer vertical slice**

```bash
git add pyproject.toml src/dashpi/server.py tests/test_server.py tests/test_local_web_e2e.py
git commit -m "feat: serve incidents on the local network"
```

## Plan Acceptance

Run:

```bash
python3 -m pytest -q
dashpi-server --data-root .tmp/dashpi --host 127.0.0.1 --port 8000
```

Accept when a browser can list a ready incident, render the escaped report, seek and resume the clip, and reproduce the stored SHA-256 with outbound internet blocked. Hotspot startup and timeout are hardware-integration work, not an unverified desktop shim.
