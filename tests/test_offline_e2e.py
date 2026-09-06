import socket

from tests.test_pipeline import pipeline_fixture


def test_injected_analysis_pipeline_never_opens_network(pipeline_fixture, monkeypatch):
    def blocked(*_args, **_kwargs):
        raise AssertionError("network attempted")

    monkeypatch.setattr(socket, "create_connection", blocked)
    pipeline, incident, segments = pipeline_fixture

    result = pipeline.process(
        incident,
        segments,
        lambda _frames: {"incident_timestamp": 3.0, "summary": "Offline", "observations": [], "limitations": []},
    )

    assert result.state.value == "ready"
