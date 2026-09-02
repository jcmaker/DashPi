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


def test_missing_configured_model_fails_startup(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self):
            return b'{"models":[{"name":"other"}]}'

    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: Response())
    with pytest.raises(ValueError, match="not installed"):
        OllamaClient("moondream").validate_model()
