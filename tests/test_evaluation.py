import json
import urllib.error

import pytest

from dashpi.ai_client import AnalysisError, RetryableAnalysisError
from dashpi.evaluation import Case, call_cost, fetch_prices, load_cases, max_cost, run, score, summary_table
from tests.media_factory import make_video


def test_score_checks_time_recall_and_forbidden_claims():
    expected = {"incident_timestamp": 10.0, "timestamp_tolerance": 1.0,
                "must_observe": ["브레이크등", "빨간불"], "must_not_claim": ["보행자"]}
    result = score(expected, 10.6,
                   [{"timestamp": 9.5, "description": "앞차 브레이크등 점등"}],
                   "앞차가 급정거했고 운전자 과실이다. 속도는 80km였다.", ["야간"])
    assert result["locate_pass"] is True and result["timestamp_error"] == pytest.approx(0.6)
    assert result["observe_recall"] == 0.5
    assert result["report_violations"] == ["과실"]
    assert result["unsupported_numbers"] == ["80"]


def test_score_without_expectations_is_neutral():
    result = score({"incident_timestamp": 3.0}, 9.0, [], "요약", [])
    assert (result["locate_pass"], result["observe_recall"], result["report_violations"]) == (False, 1.0, [])


def test_cost_helpers():
    prices = {"v": (2e-6, 10e-6), "r": (1e-6, 2e-6)}
    assert call_cost({"prompt_tokens": 1000, "completion_tokens": 100}, prices["v"]) == pytest.approx(0.003)
    single = max_cost(1, ["v"], ["r"], prices)
    assert max_cost(10, ["v"], ["r"], prices) == pytest.approx(single * 10)
    assert max_cost(1, ["v", "v"], ["r"], prices) > single


def test_cases_need_both_clip_and_expectations(tmp_path):
    good = tmp_path / "a"
    good.mkdir()
    (good / "clip.mp4").write_bytes(b"x")
    (good / "expected.json").write_text(json.dumps({"incident_timestamp": 1.0}))
    (tmp_path / "no-clip").mkdir()
    (tmp_path / "no-clip" / "expected.json").write_text("{}")
    assert [case.case_id for case in load_cases(tmp_path)] == ["a"]


def test_summary_table_lists_each_combination():
    rows = [{"case": "a", "vision_model": "v", "report_model": "r", "locate_pass": True,
             "observe_recall": 1.0, "report_violations": [], "seconds": 3.2, "cost": 0.05}]
    table = summary_table(rows)
    assert "v" in table and "r" in table and "0.05" in table


def test_eval_command_asks_before_spending(tmp_path, monkeypatch, capsys):
    import sys
    from dashpi import cli

    case = tmp_path / "cases" / "a"
    case.mkdir(parents=True)
    (case / "clip.mp4").write_bytes(b"x")
    (case / "expected.json").write_text(json.dumps({"incident_timestamp": 1.0}))
    monkeypatch.setattr("dashpi.cli.load_ai_config", lambda *_: type("C", (), {"base_url": "https://x", "api_key": "k"})())
    monkeypatch.setattr("dashpi.cli.fetch_prices", lambda models: {m: (1e-6, 1e-6) for m in models})
    monkeypatch.setattr("dashpi.cli.run_evaluation", lambda *_a, **_k: pytest.fail("must not run without consent"))
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")
    monkeypatch.setattr(sys, "argv", ["dashpi", "eval", "--cases", str(tmp_path / "cases"),
                                      "--vision-model", "v", "--report-model", "r", "--out", str(tmp_path / "o.jsonl")])
    with pytest.raises(SystemExit):
        cli.main()
    assert "예상 최대 비용" in capsys.readouterr().out


def test_run_continues_after_a_failed_model_call(tmp_path):
    clip = make_video(tmp_path / "clip.mp4", 6)
    case = Case("a", clip, {"incident_timestamp": 1.0})

    class FakeClient:
        def complete(self, model, messages, name, schema, max_tokens):
            if name == "locate":
                if model == "bad-vision":
                    raise RetryableAnalysisError("네트워크 오류")
                return ({"incident_timestamp": 1.0, "confidence": 0.9, "reason": "r"},
                        {"prompt_tokens": 10, "completion_tokens": 5})
            if name == "observe":
                return ({"observations": [{"timestamp": 1.0, "description": "d"}]},
                        {"prompt_tokens": 20, "completion_tokens": 10})
            if name == "report":
                if model == "bad-report":
                    raise AnalysisError("응답 형식 오류")
                return ({"summary": "s", "limitations": []}, {"prompt_tokens": 5, "completion_tokens": 5})
            raise AssertionError(name)

    prices = {model: (1e-6, 1e-6) for model in ("good-vision", "bad-vision", "good-report", "bad-report")}
    out_path = tmp_path / "out.jsonl"

    rows = run([case], ["good-vision", "bad-vision"], ["good-report", "bad-report"],
               FakeClient(), prices, out_path, tmp_path / "work")

    errors = [row for row in rows if "error" in row]
    successes = [row for row in rows if "error" not in row]
    assert len(rows) == 3
    assert len(errors) == 2 and len(successes) == 1
    assert successes[0]["vision_model"] == "good-vision" and successes[0]["report_model"] == "good-report"
    bad_report_error = next(row for row in errors if row["vision_model"] == "good-vision")
    assert bad_report_error["report_model"] == "bad-report" and "응답 형식 오류" in bad_report_error["error"]
    bad_vision_error = next(row for row in errors if row["vision_model"] == "bad-vision")
    assert bad_vision_error["report_model"] == "-" and "네트워크 오류" in bad_vision_error["error"]

    lines = out_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(rows)


def test_fetch_prices_wraps_network_errors(monkeypatch):
    def boom(*_args, **_kwargs):
        raise urllib.error.URLError("no network")

    monkeypatch.setattr("dashpi.evaluation.urllib.request.urlopen", boom)
    with pytest.raises(ValueError, match="가격 정보를 가져오지 못했습니다"):
        fetch_prices(["m"])


def test_summary_table_renders_error_rows():
    rows = [{"case": "a", "vision_model": "v", "report_model": "-", "error": "네트워크 오류"}]
    table = summary_table(rows)
    assert "ERROR" in table and "네트워크 오류" in table
