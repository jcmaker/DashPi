import pytest

from dashpi.reports import render_report_html, validate_report


def complete_report_fixture():
    return {
        "incident_id": "inc-1",
        "triggered_at": "2026-09-06T00:00:00Z",
        "incident_timestamp": 22.5,
        "transfer_window": {"start": 17.5, "end": 27.5},
        "summary": "<script>alert(1)</script>",
        "observations": [{"timestamp": 22.5, "description": "차량 접촉"}],
        "object_observations": [
            {
                "timestamp": 22.5,
                "track_id": 1,
                "label": "car",
                "confidence": 0.91,
                "box": [1, 2, 30, 40],
            }
        ],
        "limitations": ["단일 카메라"],
        "warnings": [],
        "overlays": {"traffic_lights": False, "lanes": False, "traffic_signs": False},
        "digests": {
            "clip.mp4": "abc",
            "annotated.mp4": "def",
            "before.jpg": "b",
            "moment.jpg": "m",
            "after.jpg": "a",
        },
        "model": "test-model",
        "generated_at": "2026-09-06T00:01:00Z",
    }


def test_report_binds_model_and_source_digest():
    report = validate_report(
        {
            "incident_timestamp": 2.5,
            "summary": "Vehicle stopped",
            "observations": [{"timestamp": 2.5, "description": "Brake lights"}],
            "limitations": ["Single camera"],
        },
        "abc",
        "moondream",
        "2026-09-02T00:00:00Z",
        clip_duration=6.0,
    )
    assert report["source_clip_sha256"] == "abc"
    assert report["model"] == "moondream"


def test_report_requires_finite_incident_offset_inside_clip():
    report = validate_report(
        {"incident_timestamp": 22.4, "summary": "충돌", "observations": [], "limitations": []},
        "abc",
        "model",
        "now",
        clip_duration=45.0,
    )

    assert report["incident_timestamp"] == 22.4


@pytest.mark.parametrize("value", [-0.1, 45.1, True, float("nan")])
def test_report_rejects_invalid_incident_offset(value):
    with pytest.raises(ValueError, match="incident timestamp"):
        validate_report(
            {"incident_timestamp": value, "summary": "x", "observations": [], "limitations": []},
            "abc",
            "model",
            "now",
            clip_duration=45.0,
        )


def test_manual_offset_replaces_failed_localization_but_not_analysis_text():
    report = validate_report(
        {"summary": "충돌", "observations": [], "limitations": ["자동 시점 탐색 실패"]},
        "abc",
        "model",
        "now",
        clip_duration=45.0,
        incident_offset_override=7.0,
    )

    assert report["incident_timestamp"] == 7.0


def test_html_escapes_model_output():
    report = complete_report_fixture()
    report["observations"] = []
    report["limitations"] = []
    html = render_report_html(report, b"video", [b"before", b"moment", b"after"])
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_html_identifies_report_provenance_and_escapes_hostile_lists():
    report = complete_report_fixture()
    report.update(
        {
            "summary": "x",
            "observations": [
                {"timestamp": 1.0, "description": "<img src=x onerror=alert(1)>"}
            ],
            "limitations": ["<script>alert(1)</script>"],
            "digests": {"clip.mp4": "clip-digest"},
            "model": "moondream",
            "generated_at": "2026-09-02T00:01:00Z",
        }
    )
    document = render_report_html(report, b"video", [b"before", b"moment", b"after"])

    assert "clip.mp4" in document and "clip-digest" in document
    assert "Model: moondream" in document
    assert "Generated: 2026-09-02T00:01:00Z" in document
    assert "AI output is advisory and may be incomplete." in document
    assert "<img src=x onerror=alert(1)>" not in document
    assert "<script>alert(1)</script>" not in document
    assert "&lt;img src=x onerror=alert(1)&gt;" in document
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in document


def test_html_embeds_video_three_frames_visual_stats_and_offline_controls():
    report = complete_report_fixture()
    document = render_report_html(report, b"video", [b"before", b"moment", b"after"])
    assert 'src="data:video/mp4;base64,dmlkZW8="' in document
    assert document.count('src="data:image/jpeg;base64,') == 3
    assert "Download HTML" in document and "Save as PDF" in document
    assert "object-chart" in document and "incident-timeline" in document
    assert "@media print" in document
    assert ".screen-only{display:none" in document
    assert "AI output is advisory" in document
    assert "<script>alert(1)</script>" not in document


def test_html_requires_exactly_three_keyframes():
    with pytest.raises(ValueError, match="three key frames"):
        render_report_html(complete_report_fixture(), b"video", [b"only one"])


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
            clip_duration=6.0,
        )


@pytest.mark.parametrize("raw", [[], "report", None])
def test_report_rejects_non_object_root(raw):
    with pytest.raises(ValueError, match="report shape"):
        validate_report(raw, "abc", "m", "now", clip_duration=6.0)


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
        validate_report(raw, "abc", "m", "now", clip_duration=6.0)


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
            clip_duration=6.0,
        )

