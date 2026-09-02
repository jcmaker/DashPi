import pytest
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError

from dashpi.reports import OllamaClient, render_report_html, validate_report


class LocalServer:
    def __init__(self, handler):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server.server_port}"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()


def test_report_binds_model_and_source_digest():
    report = validate_report(
        {
            "summary": "Vehicle stopped",
            "observations": [{"timestamp": 2.5, "description": "Brake lights"}],
            "limitations": ["Single camera"],
        },
        "abc",
        "moondream",
        "2026-09-02T00:00:00Z",
    )
    assert report["source_clip_sha256"] == "abc"
    assert report["model"] == "moondream"


def test_html_escapes_model_output():
    html = render_report_html(
        {
            "summary": "<script>alert(1)</script>",
            "observations": [],
            "limitations": [],
            "source_clip_sha256": "abc",
            "model": "m",
            "generated_at": "now",
        }
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_html_identifies_report_provenance_and_escapes_hostile_lists():
    document = render_report_html(
        {
            "summary": "x",
            "observations": [{"timestamp": 1.0, "description": "<img src=x onerror=alert(1)>"}],
            "limitations": ["<script>alert(1)</script>"],
            "source_clip_sha256": "clip-digest",
            "model": "moondream",
            "generated_at": "2026-09-02T00:01:00Z",
        }
    )

    assert "Source clip SHA-256: clip-digest" in document
    assert "Model: moondream" in document
    assert "Generated at: 2026-09-02T00:01:00Z" in document
    assert "AI output is advisory and may be incomplete." in document
    assert "<img" not in document and "<script>" not in document
    assert "&lt;img src=x onerror=alert(1)&gt;" in document
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in document


def test_report_rejects_malformed_observation():
    with pytest.raises(ValueError, match="observation"):
        validate_report(
            {
                "summary": "x",
                "observations": [{"timestamp": "soon", "description": 3}],
                "limitations": [],
            },
            "abc",
            "m",
            "now",
        )


@pytest.mark.parametrize("raw", [[], "report", None])
def test_report_rejects_non_object_root(raw):
    with pytest.raises(ValueError, match="report shape"):
        validate_report(raw, "abc", "m", "now")


@pytest.mark.parametrize(
    "raw",
    [
        {
            "summary": "x",
            "observations": [],
            "limitations": [],
            "untrusted": "extra",
        },
        {
            "summary": "x",
            "observations": [{"timestamp": 1.0, "description": "y", "untrusted": "extra"}],
            "limitations": [],
        },
    ],
)
def test_report_rejects_surplus_model_fields(raw):
    with pytest.raises(ValueError, match="report shape|observation"):
        validate_report(raw, "abc", "m", "now")


@pytest.mark.parametrize("timestamp", [True, False, float("inf"), float("-inf"), float("nan")])
def test_report_rejects_boolean_and_non_finite_timestamps(timestamp):
    with pytest.raises(ValueError, match="observation"):
        validate_report(
            {
                "summary": "x",
                "observations": [{"timestamp": timestamp, "description": "y"}],
                "limitations": [],
            },
            "abc",
            "m",
            "now",
        )


def test_missing_configured_model_fails_startup(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self):
            return b'{"models":[{"name":"other"}]}'

    class Opener:
        def open(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr("urllib.request.build_opener", lambda *_handlers: Opener())
    with pytest.raises(ValueError, match="not installed"):
        OllamaClient("moondream").validate_model()


def test_client_uses_proxy_disabled_opener_for_both_requests(monkeypatch, tmp_path):
    class Response:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self):
            return self.payload

    class Opener:
        def __init__(self):
            self.requests = []

        def open(self, request, timeout):
            self.requests.append((request, timeout))
            if isinstance(request, str):
                return Response(b'{"models":[{"name":"moondream"}]}')
            return Response(
                b'{"response":"{\\"summary\\": \\"Vehicle stopped\\", \\"observations\\": [], \\"limitations\\": []}"}'
            )

    opener = Opener()
    handlers = []

    def build_opener(*new_handlers):
        handlers.extend(new_handlers)
        return opener

    monkeypatch.setattr("urllib.request.build_opener", build_opener)
    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: pytest.fail("used global opener"))
    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"jpeg")

    client = OllamaClient("moondream")
    client.validate_model()
    report = client.analyze([frame])

    assert report["summary"] == "Vehicle stopped"
    assert [
        request if isinstance(request, str) else request.full_url
        for request, _timeout in opener.requests
    ] == ["http://127.0.0.1:11434/api/tags", "http://127.0.0.1:11434/api/generate"]
    assert handlers[0].proxies == {}


@pytest.mark.parametrize(
    "base_url",
    [
        "https://127.0.0.1:11434",
        "http://localhost:11434",
        "http://192.168.1.5:11434",
        "http://127.0.0.1:11434/api/generate",
        "http://user:pass@127.0.0.1:11434",
        "http://127.0.0.1:11434?query=yes",
        "http://127.0.0.1:11434#fragment",
    ],
)
def test_client_rejects_non_loopback_or_non_origin_base_urls(base_url):
    with pytest.raises(ValueError, match="numeric loopback HTTP origin"):
        OllamaClient("moondream", base_url)


@pytest.mark.parametrize("base_url", ["http://127.0.0.1", "http://127.0.0.1:11434", "http://[::1]:11434"])
def test_client_accepts_numeric_loopback_http_origins(base_url):
    assert OllamaClient("moondream", base_url).base_url == base_url


def test_client_sends_local_generate_request_with_expected_payload_and_timeouts(tmp_path):
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append((self.path, None))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"models":[{"name":"moondream"}]}')

        def do_POST(self):
            payload = self.rfile.read(int(self.headers["Content-Length"]))
            seen.append((self.path, payload))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"response":"{\\"summary\\": \\"Vehicle stopped\\", \\"observations\\": [], \\"limitations\\": []}"}')

        def log_message(self, *_):
            return None

    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"jpeg")
    with LocalServer(Handler) as server:
        client = OllamaClient("moondream", server.url, timeout=17.0)
        opened = []
        original_open = client.opener.open

        def record_open(request, timeout):
            opened.append((request, timeout))
            return original_open(request, timeout=timeout)

        client.opener.open = record_open
        client.validate_model()
        assert client.analyze([frame])["summary"] == "Vehicle stopped"

    assert [(request if isinstance(request, str) else request.full_url, timeout) for request, timeout in opened] == [
        (server.url + "/api/tags", 5.0),
        (server.url + "/api/generate", 17.0),
    ]
    assert seen[0] == ("/api/tags", None)
    assert seen[1][0] == "/api/generate"
    assert json.loads(seen[1][1]) == {
        "model": "moondream",
        "stream": False,
        "format": "json",
        "prompt": "Describe visible events by timestamp. Return summary, observations, limitations.",
        "images": ["anBlZw=="],
    }


def test_client_rejects_redirect_without_requesting_redirect_target(tmp_path):
    target_hits = []

    class TargetHandler(BaseHTTPRequestHandler):
        def respond(self):
            target_hits.append(self.path)
            self.send_response(200)
            self.send_header("Content-Length", "17")
            self.end_headers()
            self.wfile.write(b'{"response":"{}"}')

        do_GET = respond
        do_POST = respond

        def log_message(self, *_):
            return None

    with LocalServer(TargetHandler) as target:
        class RedirectHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.send_response(302)
                self.send_header("Location", target.url + "/escaped")
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *_):
                return None

        frame = tmp_path / "frame.jpg"
        frame.write_bytes(b"jpeg")
        with LocalServer(RedirectHandler) as redirector:
            with pytest.raises(HTTPError, match="302"):
                OllamaClient("moondream", redirector.url).analyze([frame])

    assert target_hits == []
