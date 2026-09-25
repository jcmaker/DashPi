import pytest

from dashpi.ai_client import AnalysisError, RetryableAnalysisError
from dashpi.analysis import Analyzer, FakeAnalyzer, build_analyzer, observe_window
from dashpi.reports import validate_report
from tests.media_factory import make_video


class ScriptedClient:
    """Stands in for ChatClient; answers each role from a script and records requests."""

    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def complete(self, model, messages, schema_name, schema, max_tokens, reasoning_effort="low"):
        self.calls.append((schema_name, model, messages, max_tokens))
        answer = self.answers[schema_name]
        if isinstance(answer, Exception):
            raise answer
        return answer, {"prompt_tokens": 100, "completion_tokens": 10}


ANSWERS = {
    "locate": {"incident_timestamp": 4.0, "confidence": 0.8, "reason": "앞차 급정거"},
    "observe": {"observations": [{"timestamp": 3.5, "description": "앞차 브레이크등 점등"}]},
    "report": {"summary": "앞차가 급정거했다.", "limitations": ["야간 화질 저하"]},
}


def analyzer(tmp_path, client, key="sk"):
    config = tmp_path / "ai.env"
    config.write_text(f"DASHPI_AI_API_KEY={key}\n")
    config.chmod(0o600)
    return Analyzer("vision-m", "report-m", tmp_path, config_path=config,
                    client_factory=lambda *_args, **_kw: client)


def frames_for(clip, tmp_path):
    from dashpi.media import sample_frames
    return sample_frames(clip, tmp_path / "frames", 12)


def test_roles_run_in_order_and_result_passes_report_validation(tmp_path):
    clip = make_video(tmp_path / "clip.mp4", 8)
    client = ScriptedClient(ANSWERS)
    result = analyzer(tmp_path, client)(frames_for(clip, tmp_path), clip, tmp_path / "work")

    assert [name for name, *_ in client.calls] == ["locate", "observe", "report"]
    assert [model for _name, model, *_ in client.calls] == ["vision-m", "vision-m", "report-m"]
    assert result["analysis"]["locate"] == {"confidence": 0.8, "reason": "앞차 급정거"}
    raw = {key: result[key] for key in ("incident_timestamp", "summary", "observations", "limitations")}
    assert validate_report(raw, "0" * 64, "label", "now", 8.0)["incident_timestamp"] == 4.0


def test_observe_frames_come_from_the_window_around_the_moment(tmp_path):
    clip = make_video(tmp_path / "clip.mp4", 8)
    client = ScriptedClient(ANSWERS)
    analyzer(tmp_path, client)(frames_for(clip, tmp_path), clip, tmp_path / "work")

    observe_text = " ".join(part["text"] for part in client.calls[1][2][1]["content"] if part["type"] == "text")
    stamps = [float(token.removesuffix("초")) for token in observe_text.split() if token.endswith("초")]
    assert len(stamps) == 12 and min(stamps) >= 1.0 and max(stamps) <= 7.0


def test_role_timing_and_tokens_are_logged_without_the_key(tmp_path, caplog):
    import logging
    caplog.set_level(logging.INFO, logger="dashpi")
    clip = make_video(tmp_path / "clip.mp4", 8)
    analyzer(tmp_path, ScriptedClient(ANSWERS), key="sk-secret")(frames_for(clip, tmp_path), clip, tmp_path / "w")
    assert "AI observe: vision-m" in caplog.text and "토큰 100/10" in caplog.text
    assert "sk-secret" not in caplog.text


def test_manual_moment_skips_locating(tmp_path):
    clip = make_video(tmp_path / "clip.mp4", 8)
    client = ScriptedClient(ANSWERS)
    result = analyzer(tmp_path, client)(frames_for(clip, tmp_path), clip, tmp_path / "work", 2.5)

    assert [name for name, *_ in client.calls] == ["observe", "report"]
    assert result["incident_timestamp"] == 2.5


def test_missing_key_waits_before_any_call_or_budget_use(tmp_path):
    clip = make_video(tmp_path / "clip.mp4", 4)
    client = ScriptedClient(ANSWERS)
    with pytest.raises(RetryableAnalysisError, match="API 키"):
        analyzer(tmp_path, client, key="")(frames_for(clip, tmp_path), clip, tmp_path / "w")
    assert client.calls == [] and not (tmp_path / "ai-usage.json").exists()


def test_locate_answer_outside_the_clip_fails(tmp_path):
    clip = make_video(tmp_path / "clip.mp4", 4)
    client = ScriptedClient({**ANSWERS, "locate": {"incident_timestamp": 99.0, "confidence": 1.0, "reason": "x"}})
    with pytest.raises(AnalysisError, match="사고 시각"):
        analyzer(tmp_path, client)(frames_for(clip, tmp_path), clip, tmp_path / "w")


@pytest.mark.parametrize("moment,duration,expected", [
    (4.0, 8.0, (1.0, 7.0)),
    (0.2, 8.0, (0.0, 3.2)),
    (7.9, 8.0, (4.9, 8.0)),
    (0.3, 0.6, (0.0, 0.6)),
])
def test_observe_window_stays_inside_the_clip(moment, duration, expected):
    assert observe_window(moment, duration) == pytest.approx(expected)


def test_fake_model_needs_no_network_and_validates(tmp_path):
    clip = make_video(tmp_path / "clip.mp4", 6)
    fake = build_analyzer("fake", "anything", tmp_path)
    assert isinstance(fake, FakeAnalyzer)
    result = fake([], clip, tmp_path / "w")
    raw = {key: result[key] for key in ("incident_timestamp", "summary", "observations", "limitations")}
    validate_report(raw, "0" * 64, "fake", "now", 6.0)
