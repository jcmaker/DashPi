"""Incident analysis in three gradeable roles: locate the moment, observe the scene, summarize."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import logging
import math
from pathlib import Path
import time

from dashpi.ai_budget import DailyBudget
from dashpi.ai_client import (
    DEFAULT_CONFIG_PATH, AnalysisError, ChatClient, RetryableAnalysisError, load_ai_config,
)
from dashpi.media import probe_duration, sample_frames

log = logging.getLogger("dashpi")
FAKE_MODEL = "fake"
OBSERVE_SECONDS = 3.0
FRAME_COUNT = 12
MAX_TOKENS = {"locate": 300, "observe": 1500, "report": 1200}
RULES = (
    "당신은 블랙박스 사고 영상 분석 보조입니다. 화면에 보이는 사실만 쓰고, 보이지 않는 것은 추측하지 마세요. "
    "법적 과실이나 책임을 판단하지 마세요. 모든 문장은 한국어로 쓰세요."
)


def _object(properties: dict) -> dict:
    return {"type": "object", "properties": properties, "required": list(properties),
            "additionalProperties": False}


LOCATE_SCHEMA = _object({
    "incident_timestamp": {"type": "number"},
    "confidence": {"type": "number"},
    "reason": {"type": "string"},
})
OBSERVE_SCHEMA = _object({
    "observations": {"type": "array", "items": _object({
        "timestamp": {"type": "number"}, "description": {"type": "string"},
    })},
})
REPORT_SCHEMA = _object({
    "summary": {"type": "string"},
    "limitations": {"type": "array", "items": {"type": "string"}},
})


@dataclass(frozen=True)
class RoleResult:
    output: dict
    usage: dict
    seconds: float
    model: str


def _frame_content(instruction: str, frames: list[tuple[Path, float]]) -> list[dict]:
    content = [{"type": "text", "text": instruction}]
    for path, timestamp in frames:
        content.append({"type": "text", "text": f"{timestamp:.2f}초"})
        encoded = base64.b64encode(path.read_bytes()).decode()
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}})
    return content


def _run(client, model: str, name: str, schema: dict, content) -> RoleResult:
    started = time.monotonic()
    output, usage = client.complete(
        model, [{"role": "system", "content": RULES}, {"role": "user", "content": content}],
        name, schema, MAX_TOKENS[name],
    )
    missing = [key for key in schema["required"] if key not in output]
    if missing:
        raise AnalysisError(f"응답 형식 오류: {', '.join(missing)} 누락")
    return RoleResult(output, usage, time.monotonic() - started, model)


def locate(client, model: str, frames: list[tuple[Path, float]]) -> RoleResult:
    instruction = ("각 이미지 앞의 숫자는 증거 클립 시작(0초) 기준 시각입니다. 충돌·급정거·급회피 등 사고 순간의 "
                   "시각(초)을 incident_timestamp로, 확신도(0~1)를 confidence로, 짧은 근거를 reason으로 답하세요.")
    return _run(client, model, "locate", LOCATE_SCHEMA, _frame_content(instruction, frames))


def observe(client, model: str, frames: list[tuple[Path, float]]) -> RoleResult:
    instruction = ("사고 순간 전후 프레임입니다. 차량·보행자·신호·차선·도로·날씨·움직임에 대해 보이는 사실을 "
                   "시각(초, 클립 기준)과 함께 observations로 나열하세요. 판단이나 추측은 쓰지 마세요.")
    return _run(client, model, "observe", OBSERVE_SCHEMA, _frame_content(instruction, frames))


def summarize(client, model: str, observations: list[dict]) -> RoleResult:
    instruction = ("다음 관찰 목록만 근거로 운전자가 읽을 사고 요약(summary)과 이 분석의 한계(limitations)를 쓰세요. "
                   "관찰에 없는 사실·숫자·고유명사를 추가하지 마세요.\n"
                   + json.dumps(observations, ensure_ascii=False))
    return _run(client, model, "report", REPORT_SCHEMA, instruction)


def observe_window(moment: float, duration: float) -> tuple[float, float]:
    start = max(0.0, moment - OBSERVE_SECONDS)
    end = min(duration, moment + OBSERVE_SECONDS)
    return (0.0, duration) if end - start < 1.0 else (start, end)


class Analyzer:
    def __init__(self, vision_model: str, report_model: str, data_root: Path,
                 config_path: Path = DEFAULT_CONFIG_PATH, client_factory=ChatClient):
        self.vision_model, self.report_model = vision_model, report_model
        self.data_root, self.config_path, self.client_factory = data_root, config_path, client_factory

    def __call__(self, frames, clip_path: Path, frame_dir: Path,
                 incident_offset_override: float | None = None) -> dict:
        config = load_ai_config(self.config_path)  # re-read so a key added later is picked up
        DailyBudget(self.data_root / "ai-usage.json", config.daily_limit).consume()
        client = self.client_factory(config.base_url, config.api_key)
        duration = probe_duration(clip_path)
        steps = []
        if incident_offset_override is None:
            located = locate(client, self.vision_model, frames)
            moment = located.output["incident_timestamp"]
            if isinstance(moment, bool) or not isinstance(moment, (int, float)) \
                    or not math.isfinite(moment) or not 0.0 <= moment <= duration:
                raise AnalysisError("모델이 준 사고 시각이 클립 밖입니다")
            steps.append(("locate", located))
        else:
            moment = incident_offset_override
        start, end = observe_window(moment, duration)
        dense = sample_frames(clip_path, frame_dir / "observe", FRAME_COUNT, start, end)
        observed = observe(client, self.vision_model, dense)
        reported = summarize(client, self.report_model, observed.output["observations"])
        steps += [("observe", observed), ("report", reported)]
        for name, result in steps:  # never log the key or image content
            log.info("AI %s: %s %.1fs 토큰 %s/%s", name, result.model, result.seconds,
                     result.usage.get("prompt_tokens"), result.usage.get("completion_tokens"))
        analysis = {
            "models": {name: result.model for name, result in steps},
            "usage": {name: result.usage for name, result in steps},
            "seconds": {name: round(result.seconds, 2) for name, result in steps},
        }
        if incident_offset_override is None:
            analysis["locate"] = {key: steps[0][1].output[key] for key in ("confidence", "reason")}
        return {
            "incident_timestamp": moment,
            "summary": reported.output["summary"],
            "observations": observed.output["observations"],
            "limitations": reported.output["limitations"],
            "analysis": analysis,
        }


class FakeAnalyzer:
    """Deterministic offline stand-in so teammates can exercise the whole flow for free."""

    def __call__(self, frames, clip_path: Path, frame_dir: Path,
                 incident_offset_override: float | None = None) -> dict:
        duration = probe_duration(clip_path)
        moment = duration / 2 if incident_offset_override is None else incident_offset_override
        return {
            "incident_timestamp": moment,
            "summary": "가짜 분석기 결과입니다. 실제 영상 내용이 아닙니다.",
            "observations": [{"timestamp": moment, "description": "가짜 관찰"}],
            "limitations": ["테스트용 가짜 분석 결과"],
            "analysis": {"models": {"all": FAKE_MODEL}},
        }


def build_analyzer(vision_model: str, report_model: str, data_root: Path):
    if vision_model == FAKE_MODEL:
        return FakeAnalyzer()
    return Analyzer(vision_model, report_model, data_root)


def api_key_configured(config_path: Path = DEFAULT_CONFIG_PATH) -> bool:
    try:
        load_ai_config(config_path)
        return True
    except (RetryableAnalysisError, AnalysisError):
        return False
