"""OpenAI-compatible chat client for incident analysis (OpenRouter by default)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
import ipaddress
import json
import logging
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger("dashpi")

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_CONFIG_PATH = Path.home() / ".config" / "dashpi" / "ai.env"
DEFAULT_DAILY_LIMIT = 20
_RETRY_MINUTES = (1, 2, 5, 10, 30)
_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.S)


class AnalysisError(Exception):
    """Analysis failed in a way retrying will not fix; the evidence clip stays preserved."""


class RetryableAnalysisError(Exception):
    """Analysis could not run now (offline, provider busy, no key, daily limit); try again later."""

    def __init__(self, message: str, retry_at: datetime | None = None, reached_provider: bool = True):
        super().__init__(message)
        # False only when the request never left the device, so it cannot have been billed
        self.retry_at, self.reached_provider = retry_at, reached_provider


@dataclass(frozen=True)
class AIConfig:
    api_key: str
    base_url: str
    daily_limit: int


def retry_delay(attempt: int) -> timedelta:
    return timedelta(minutes=_RETRY_MINUTES[min(max(attempt, 1), len(_RETRY_MINUTES)) - 1])


def _read_env_file(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    if path.stat().st_mode & 0o077:
        log.warning("AI 키 파일 권한이 넓습니다: chmod 600 %s", path)
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def _valid_base_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    loopback = False
    try:
        loopback = parsed.hostname is not None and ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        pass
    if parsed.scheme == "https" or (parsed.scheme == "http" and loopback):
        return url.rstrip("/")
    raise AnalysisError("AI base URL은 https여야 합니다")


def load_ai_config(path: Path = DEFAULT_CONFIG_PATH, environ: Mapping[str, str] = os.environ) -> AIConfig:
    values = _read_env_file(path)
    values.update({key: value for key, value in environ.items() if key.startswith("DASHPI_AI_")})
    api_key = values.get("DASHPI_AI_API_KEY", "").strip()
    if not api_key:
        raise RetryableAnalysisError("API 키 없음")
    try:
        daily_limit = int(values.get("DASHPI_AI_DAILY_LIMIT", DEFAULT_DAILY_LIMIT))
    except ValueError as error:
        raise AnalysisError("DASHPI_AI_DAILY_LIMIT 값이 숫자가 아닙니다") from error
    return AIConfig(api_key, _valid_base_url(values.get("DASHPI_AI_BASE_URL", DEFAULT_BASE_URL)), daily_limit)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def _http_error(status: int) -> Exception:
    if status in (408, 429) or status >= 500:
        return RetryableAnalysisError(f"분석 서버 일시 오류 (HTTP {status})")
    if status in (401, 403):
        return AnalysisError(f"API 키 확인 필요 (HTTP {status})")
    if status == 402:
        return AnalysisError("크레딧 부족 (HTTP 402)")
    return AnalysisError(f"분석 요청 거부 (HTTP {status})")


class ChatClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 60.0):
        self.base_url = _valid_base_url(base_url)
        if not api_key or any(ord(char) < 32 or ord(char) == 127 for char in api_key):
            raise AnalysisError("API 키 형식 오류")
        self.api_key, self.timeout = api_key, timeout
        self.opener = urllib.request.build_opener(_NoRedirect())  # env proxies still apply

    def complete(self, model: str, messages: list[dict], schema_name: str, schema: dict,
                 max_tokens: int, reasoning_effort: str = "low") -> tuple[dict, dict]:
        body = json.dumps({
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "reasoning": {"effort": reasoning_effort},
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": schema_name, "strict": True, "schema": schema}},
            "provider": {"data_collection": "deny"},
        }).encode()
        request = urllib.request.Request(
            self.base_url + "/chat/completions", data=body,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
                     "X-Title": "DashPi"},
        )
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = json.loads(response.read())
        except urllib.error.HTTPError as error:
            raise _http_error(error.code) from error
        except urllib.error.URLError as error:
            if isinstance(error.reason, TimeoutError):
                raise RetryableAnalysisError("인터넷 연결 없음") from error
            raise RetryableAnalysisError("인터넷 연결 없음", reached_provider=False) from error
        except TimeoutError as error:  # read timeout: the provider may already be working (and billing)
            raise RetryableAnalysisError("인터넷 연결 없음") from error
        except (ConnectionError, OSError) as error:
            raise RetryableAnalysisError("인터넷 연결 없음", reached_provider=False) from error
        except ValueError as error:
            raise AnalysisError("응답 형식 오류") from error
        return self._parse(raw)

    @staticmethod
    def _parse(raw: object) -> tuple[dict, dict]:
        if not isinstance(raw, dict):
            raise AnalysisError("응답 형식 오류")
        if isinstance(raw.get("error"), dict):
            code = raw["error"].get("code")
            raise _http_error(code if isinstance(code, int) else 400)
        try:
            choice = raw["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError, TypeError) as error:
            raise AnalysisError("응답 형식 오류") from error
        if message.get("refusal"):
            raise AnalysisError("모델이 분석을 거부했습니다")
        if choice.get("finish_reason") == "length":
            raise AnalysisError("응답이 잘림 (max_tokens 부족)")
        content = message.get("content") or ""
        fenced = _FENCE.match(content)
        try:
            parsed = json.loads(fenced.group(1) if fenced else content)
        except ValueError as error:
            raise AnalysisError("응답 형식 오류") from error
        if not isinstance(parsed, dict):
            raise AnalysisError("응답 형식 오류")
        return parsed, raw.get("usage") or {}
