"""Evaluation harness: run analysis roles over labelled cases and grade quality, latency, cost."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import time
import urllib.error
import urllib.request

from dashpi.ai_client import AnalysisError, RetryableAnalysisError
from dashpi.analysis import FRAME_COUNT, MAX_TOKENS, locate, observe, observe_window, summarize
from dashpi.media import probe_duration, sample_frames

PRICES_URL = "https://openrouter.ai/api/v1/models"
IMAGE_TOKEN_CEILING = 1100  # per 1024px frame; conservative for max-cost estimates
PROMPT_TOKEN_CEILING = 1000
DEFAULT_FORBIDDEN = ("과실", "책임", "잘못")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


@dataclass(frozen=True)
class Case:
    case_id: str
    clip: Path
    expected: dict


def load_cases(root: Path) -> list[Case]:
    cases = []
    for folder in sorted(path for path in root.iterdir() if path.is_dir()):
        clip, expected = folder / "clip.mp4", folder / "expected.json"
        if clip.is_file() and expected.is_file():
            cases.append(Case(folder.name, clip, json.loads(expected.read_text(encoding="utf-8"))))
    return cases


def score(expected: dict, moment: float, observations: list[dict], summary: str,
          limitations: list[str]) -> dict:
    error = abs(moment - float(expected["incident_timestamp"]))
    observed = " ".join(item["description"] for item in observations)
    must_observe = expected.get("must_observe", [])
    forbidden = list(expected.get("must_not_claim", [])) + list(DEFAULT_FORBIDDEN)
    report_text = " ".join([summary, *limitations])
    return {
        "timestamp_error": error,
        "locate_pass": error <= float(expected.get("timestamp_tolerance", 1.0)),
        "observe_recall": sum(term in observed for term in must_observe) / len(must_observe) if must_observe else 1.0,
        "observe_violations": [term for term in forbidden if term in observed],
        "report_violations": [term for term in forbidden if term in report_text],
        "unsupported_numbers": [n for n in _NUMBER.findall(summary) if n not in observed],
    }


def call_cost(usage: dict, price: tuple[float, float]) -> float:
    return usage.get("prompt_tokens", 0) * price[0] + usage.get("completion_tokens", 0) * price[1]


def max_cost(case_count: int, vision_models: list[str], report_models: list[str],
             prices: dict[str, tuple[float, float]]) -> float:
    vision_input = FRAME_COUNT * IMAGE_TOKEN_CEILING + PROMPT_TOKEN_CEILING
    per_case = 0.0
    for model in vision_models:
        per_case += call_cost({"prompt_tokens": vision_input, "completion_tokens": MAX_TOKENS["locate"]}, prices[model])
        per_case += call_cost({"prompt_tokens": vision_input, "completion_tokens": MAX_TOKENS["observe"]}, prices[model])
        for report in report_models:
            per_case += call_cost({"prompt_tokens": 3 * PROMPT_TOKEN_CEILING,
                                   "completion_tokens": MAX_TOKENS["report"]}, prices[report])
    return per_case * case_count


def fetch_prices(models: list[str]) -> dict[str, tuple[float, float]]:
    try:
        with urllib.request.urlopen(PRICES_URL, timeout=30) as response:
            listing = {item["id"]: item["pricing"] for item in json.loads(response.read())["data"]}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError) as error:
        raise ValueError(f"가격 정보를 가져오지 못했습니다: {error}") from error
    missing = [model for model in models if model not in listing]
    if missing:
        raise ValueError(f"가격을 찾을 수 없는 모델: {', '.join(missing)}")
    return {model: (float(listing[model]["prompt"]), float(listing[model]["completion"])) for model in models}


def _error_row(case_id: str, vision_model: str, report_model: str, error: Exception) -> dict:
    return {"case": case_id, "vision_model": vision_model, "report_model": report_model,
            "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "error": str(error)}


def run(cases: list[Case], vision_models: list[str], report_models: list[str], client,
        prices: dict[str, tuple[float, float]], out_path: Path, work_root: Path) -> list[dict]:
    rows = []
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a", encoding="utf-8") as out:
        def emit(row: dict) -> None:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            rows.append(row)

        for case in cases:
            duration = probe_duration(case.clip)
            frames = sample_frames(case.clip, work_root / case.case_id / "locate", FRAME_COUNT)
            for vision in vision_models:
                try:
                    located = locate(client, vision, frames)
                    moment = min(max(float(located.output["incident_timestamp"]), 0.0), duration)
                    start, end = observe_window(moment, duration)
                    dense = sample_frames(case.clip, work_root / case.case_id / f"observe-{start:.2f}",
                                          FRAME_COUNT, start, end)
                    observed = observe(client, vision, dense)
                except (AnalysisError, RetryableAnalysisError) as error:
                    emit(_error_row(case.case_id, vision, "-", error))
                    continue
                for report_model in report_models:
                    try:
                        reported = summarize(client, report_model, observed.output["observations"])
                    except (AnalysisError, RetryableAnalysisError) as error:
                        emit(_error_row(case.case_id, vision, report_model, error))
                        continue
                    roles = {"locate": located, "observe": observed, "report": reported}
                    row = {
                        "case": case.case_id, "vision_model": vision, "report_model": report_model,
                        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                        "moment": moment, "locate": located.output,
                        "observations": observed.output["observations"], "report": reported.output,
                        "seconds": round(located.seconds + observed.seconds + reported.seconds, 2),
                        "usage": {name: result.usage for name, result in roles.items()},
                        "seconds_by_role": {name: round(result.seconds, 2) for name, result in roles.items()},
                        "cost": round(call_cost(located.usage, prices[vision]) + call_cost(observed.usage, prices[vision])
                                      + call_cost(reported.usage, prices[report_model]), 5),
                        **score(case.expected, moment, observed.output["observations"],
                                reported.output["summary"], reported.output["limitations"]),
                    }
                    emit(row)
    return rows


def summary_table(rows: list[dict]) -> str:
    lines = ["case\tvision\treport\tlocate\trecall\tviolations\tseconds\tcost"]
    for row in rows:
        if "error" in row:
            message = row["error"].replace("\n", " ")
            lines.append(
                f"{row['case']}\t{row['vision_model']}\t{row['report_model']}\t"
                f"ERROR\t-\t-\t-\t-\t{message}"
            )
            continue
        lines.append(
            f"{row['case']}\t{row['vision_model']}\t{row['report_model']}\t"
            f"{'OK' if row['locate_pass'] else 'X'}\t{row['observe_recall']:.2f}\t"
            f"{len(row['report_violations'])}\t{row['seconds']}\t${row['cost']:.4f}"
        )
    return "\n".join(lines)
