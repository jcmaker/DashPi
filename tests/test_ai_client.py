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


def test_malformed_base_url_fails_up_front():
    with pytest.raises(AnalysisError, match="base URL"):
        ChatClient("not-a-valid-url", "sk")


def test_control_character_in_api_key_fails_up_front():
    with pytest.raises(AnalysisError, match="API 키 형식"):
        ChatClient("https://openrouter.ai/api/v1", "sk\nx")


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
