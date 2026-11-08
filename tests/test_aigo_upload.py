import json
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from zoneinfo import ZoneInfo

import pytest

from dashpi.aigo_upload import (
    AigoClient, AigoConfig, UploadDeferred, UploadRejected, load_aigo_config, next_day_0005,
)

KEY = "ak_test_123"


def fake_aigo(seen, create=(201, None), put=200, submit=(200, {"id": 7, "status": "queued"})):
    """AIGO API와 presigned PUT을 한 서버로 흉내 낸다. 상태 코드나 응답을 바꿔 오류를 만든다."""

    class Handler(BaseHTTPRequestHandler):
        def _reply(self, status, body=None):
            payload = json.dumps(body or {}).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _record(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            seen.append((self.command, self.path, dict(self.headers), body))
            return body

        def do_POST(self):
            body = self._record()
            if self.path == "/api/v1/analyses":
                status, reply = create
                host = f"http://127.0.0.1:{self.server.server_port}"
                self._reply(status, reply or {"id": 7, "upload_url": f"{host}/upload/7?sig=x",
                                              "upload_headers": {"Content-Type": "video/mp4"},
                                              "expires_at": "2026-11-08T00:15:00Z", "echo": json.loads(body)})
            else:
                self._reply(*submit)

        def do_PUT(self):
            self._record()
            self._reply(put)

        def log_message(self, *_args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture
def clip(tmp_path):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"v" * 1000)
    return path


def client_for(server):
    return AigoClient(AigoConfig(f"http://127.0.0.1:{server.server_port}", KEY))


def test_config_missing_key_returns_none(tmp_path):
    (tmp_path / "aigo.env").write_text("DASHPI_AIGO_API_URL=https://aigo.example\n")
    assert load_aigo_config(tmp_path / "aigo.env", environ={}) is None


def test_config_reads_file_and_env_overrides(tmp_path):
    path = tmp_path / "aigo.env"
    path.write_text("DASHPI_AIGO_API_URL=https://file.example/\nDASHPI_AIGO_API_KEY=ak_file\n")
    assert load_aigo_config(path, environ={}) == AigoConfig("https://file.example", "ak_file")
    assert load_aigo_config(path, environ={"DASHPI_AIGO_API_KEY": "ak_env"}).api_key == "ak_env"


def test_config_rejects_plain_http_unless_loopback(tmp_path):
    path = tmp_path / "aigo.env"
    path.write_text("DASHPI_AIGO_API_URL=http://aigo.example\nDASHPI_AIGO_API_KEY=ak_x\n")
    assert load_aigo_config(path, environ={}) is None
    path.write_text("DASHPI_AIGO_API_URL=http://127.0.0.1:8000\nDASHPI_AIGO_API_KEY=ak_x\n")
    assert load_aigo_config(path, environ={}).api_url == "http://127.0.0.1:8000"


def test_upload_runs_create_put_submit(clip):
    seen = []
    server = fake_aigo(seen)
    try:
        assert client_for(server).upload(clip) == 7
    finally:
        server.shutdown()
    (m1, p1, h1, b1), (m2, p2, h2, b2), (m3, p3, h3, _) = seen
    assert (m1, p1) == ("POST", "/api/v1/analyses")
    assert json.loads(b1) == {"filename": "clip.mp4", "size": 1000, "consent": True}
    assert h1["Authorization"] == f"Bearer {KEY}"
    assert (m2, p2) == ("PUT", "/upload/7?sig=x")
    assert b2 == b"v" * 1000 and h2["Content-Type"] == "video/mp4"
    assert "Authorization" not in h2
    assert (m3, p3) == ("POST", "/api/v1/analyses/7/submit")
    assert h3["Authorization"] == f"Bearer {KEY}"


def test_429_defers_to_next_day_0005(clip):
    server = fake_aigo([], create=(429, {"code": "DAILY_LIMIT", "message": "한도"}))
    try:
        with pytest.raises(UploadDeferred) as caught:
            client_for(server).upload(clip)
    finally:
        server.shutdown()
    assert caught.value.retry_at is not None
    assert caught.value.retry_at.hour == 0 and caught.value.retry_at.minute == 5


def test_next_day_0005_is_local_midnight_plus_five():
    seoul = ZoneInfo("Asia/Seoul")
    assert next_day_0005(datetime(2026, 11, 8, 23, 59, tzinfo=seoul)) == datetime(2026, 11, 9, 0, 5, tzinfo=seoul)


@pytest.mark.parametrize("kwargs", [{"create": (500, None)}, {"create": (408, None)}, {"create": (503, None)},
                                    {"submit": (502, {})}, {"put": 403}])
def test_server_errors_and_expired_put_defer(clip, kwargs):
    server = fake_aigo([], **kwargs)
    try:
        with pytest.raises(UploadDeferred) as caught:
            client_for(server).upload(clip)
    finally:
        server.shutdown()
    assert caught.value.retry_at is None


def test_network_error_defers(clip):
    client = AigoClient(AigoConfig("http://127.0.0.1:9", KEY), timeout=2)
    with pytest.raises(UploadDeferred):
        client.upload(clip)


@pytest.mark.parametrize("status", [401, 403])
def test_auth_errors_reject(clip, status):
    server = fake_aigo([], create=(status, {"code": "UNAUTHORIZED", "message": "로그인이 필요합니다."}))
    try:
        with pytest.raises(UploadRejected) as caught:
            client_for(server).upload(clip)
    finally:
        server.shutdown()
    assert caught.value.auth and str(caught.value) == "AIGO 키 확인 필요"


def test_other_4xx_rejects_with_server_message(clip):
    server = fake_aigo([], create=(400, {"code": "VIDEO_TOO_LARGE", "message": "영상은 200MB 이하여야 합니다."}))
    try:
        with pytest.raises(UploadRejected) as caught:
            client_for(server).upload(clip)
    finally:
        server.shutdown()
    assert not caught.value.auth and str(caught.value) == "영상은 200MB 이하여야 합니다."


# ---- 업로드 대기열 (aigo.json) ----
from datetime import UTC, timedelta  # noqa: E402

from dashpi.aigo_upload import AIGO_STATE, AigoUploader, mark_pending, read_state  # noqa: E402
from dashpi.models import FileArtifact, IncidentMetadata, IncidentState  # noqa: E402
from dashpi.storage import IncidentStore, atomic_write  # noqa: E402

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)


class FakeClient:
    def __init__(self, *results):
        self.results, self.calls = list(results), []

    def upload(self, clip):
        self.calls.append(clip)
        result = self.results.pop(0) if self.results else 7
        if isinstance(result, Exception):
            raise result
        return result


def incident(store, incident_id="inc1", state=IncidentState.READY):
    item = IncidentMetadata.new(incident_id, NOW.isoformat(), 10.0, 15.0)
    clip = atomic_write(store.directory(incident_id) / "clip.mp4", b"v" * 100)
    item.clip = FileArtifact(clip.path, clip.byte_length, clip.sha256, 45.0)
    item.transition(state, NOW.isoformat())
    store.save(item)
    return item


def run(uploader):
    started = uploader.tick()
    if started:
        uploader.running.result(timeout=5)
    return started


@pytest.fixture
def store(tmp_path):
    return IncidentStore(tmp_path)


def test_mark_pending_is_idempotent(store):
    incident(store)
    mark_pending(store, "inc1")
    atomic_write(store.directory("inc1") / AIGO_STATE, json.dumps({"state": "uploaded", "analysis_id": 3}).encode())
    mark_pending(store, "inc1")
    assert read_state(store, "inc1")["state"] == "uploaded"


def test_no_state_file_is_never_uploaded(store):
    incident(store)
    client = FakeClient()
    assert run(AigoUploader(store, client, now=lambda: NOW)) is None
    assert client.calls == []


def test_success_marks_uploaded_and_never_retries(store):
    incident(store)
    mark_pending(store, "inc1")
    client = FakeClient(42)
    uploader = AigoUploader(store, client, now=lambda: NOW)
    assert run(uploader) == "inc1"
    state = read_state(store, "inc1")
    assert state["state"] == "uploaded" and state["analysis_id"] == 42 and state["uploaded_at"] == NOW.isoformat()
    assert client.calls == [store.directory("inc1") / "clip.mp4"]
    assert run(uploader) is None and len(client.calls) == 1


def test_deferred_backs_off_with_retry_delay(store):
    incident(store)
    mark_pending(store, "inc1")
    clock = [NOW]
    client = FakeClient(UploadDeferred("인터넷 연결 없음"), UploadDeferred("인터넷 연결 없음"))
    uploader = AigoUploader(store, client, now=lambda: clock[0])
    run(uploader)
    state = read_state(store, "inc1")
    assert state["state"] == "pending" and state["attempts"] == 1 and state["reason"] == "인터넷 연결 없음"
    assert state["next_attempt_at"] == (NOW + timedelta(minutes=1)).isoformat()
    assert run(uploader) is None  # 아직 시각 전
    clock[0] = NOW + timedelta(minutes=1)
    run(uploader)
    assert read_state(store, "inc1")["next_attempt_at"] == (clock[0] + timedelta(minutes=2)).isoformat()


def test_deferred_with_retry_at_uses_it(store):
    incident(store)
    mark_pending(store, "inc1")
    later = NOW + timedelta(hours=12)
    run(AigoUploader(store, FakeClient(UploadDeferred("한도", retry_at=later)), now=lambda: NOW))
    assert read_state(store, "inc1")["next_attempt_at"] == later.isoformat()


def test_auth_rejection_fails_then_recover_requeues_once(store):
    incident(store)
    mark_pending(store, "inc1")
    client = FakeClient(UploadRejected("AIGO 키 확인 필요", auth=True))
    uploader = AigoUploader(store, client, now=lambda: NOW)
    run(uploader)
    assert read_state(store, "inc1")["state"] == "failed"
    assert run(uploader) is None
    uploader.recover()
    assert read_state(store, "inc1")["state"] == "pending"
    run(uploader)
    assert read_state(store, "inc1")["state"] == "uploaded"


def test_other_rejection_is_not_recovered(store):
    incident(store)
    mark_pending(store, "inc1")
    uploader = AigoUploader(store, FakeClient(UploadRejected("영상은 200MB 이하여야 합니다.")), now=lambda: NOW)
    run(uploader)
    uploader.recover()
    state = read_state(store, "inc1")
    assert state["state"] == "failed" and state["reason"] == "영상은 200MB 이하여야 합니다."


def test_digest_mismatch_fails_without_request(store):
    incident(store)
    mark_pending(store, "inc1")
    (store.directory("inc1") / "clip.mp4").write_bytes(b"tampered")
    client = FakeClient()
    run(AigoUploader(store, client, now=lambda: NOW))
    assert client.calls == []
    assert read_state(store, "inc1")["state"] == "failed"


def test_submit_failure_stays_pending(store):
    incident(store)
    mark_pending(store, "inc1")
    run(AigoUploader(store, FakeClient(UploadDeferred("AIGO 일시 오류 (HTTP 502)")), now=lambda: NOW))
    state = read_state(store, "inc1")
    assert state["state"] == "pending" and "analysis_id" not in state


def test_upload_does_not_touch_metadata(store):
    incident(store)
    mark_pending(store, "inc1")
    before = (store.directory("inc1") / "metadata.json").read_bytes()
    run(AigoUploader(store, FakeClient(9), now=lambda: NOW))
    assert (store.directory("inc1") / "metadata.json").read_bytes() == before


def test_one_upload_at_a_time_earliest_first(store):
    gate = threading.Event()

    class SlowClient(FakeClient):
        def upload(self, clip):
            gate.wait(5)
            return super().upload(clip)

    for name in ("inc1", "inc2"):
        incident(store, name)
        mark_pending(store, name)
    atomic_write(store.directory("inc1") / AIGO_STATE,
                 json.dumps({"state": "pending", "attempts": 1,
                             "next_attempt_at": (NOW - timedelta(minutes=1)).isoformat()}).encode())
    client = SlowClient()
    uploader = AigoUploader(store, client, now=lambda: NOW)
    assert uploader.tick() == "inc2"  # 재시도 시각이 없는(새) 항목이 먼저
    assert uploader.tick() is None
    gate.set()
    uploader.running.result(timeout=5)
    assert run(uploader) == "inc1"
    uploader.close()


def test_deleted_incident_is_skipped(store):
    incident(store)
    mark_pending(store, "inc1")
    (store.directory("inc1") / "metadata.json").unlink()
    client = FakeClient()
    run(AigoUploader(store, client, now=lambda: NOW))
    assert client.calls == []
