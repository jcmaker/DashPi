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
