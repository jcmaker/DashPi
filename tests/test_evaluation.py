import json

import pytest

from dashpi.evaluation import Case, call_cost, load_cases, max_cost, score, summary_table


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
