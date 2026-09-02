import pytest

from dashpi.reports import OllamaClient, render_report_html, validate_report


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
