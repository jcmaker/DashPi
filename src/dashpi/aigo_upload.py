"""사고 클립을 AIGO 서버에 올린다. 설정이 있을 때만 켜지고, Pi 로컬 분석과 따로 돈다."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, time, timedelta
import http.client
import json
import logging
import os
from pathlib import Path
import urllib.error
import urllib.request

from dashpi.ai_client import AnalysisError, _NoRedirect, _read_env_file, _valid_base_url

log = logging.getLogger("dashpi")

DEFAULT_AIGO_CONFIG = Path.home() / ".config" / "dashpi" / "aigo.env"
AUTH_REASON = "AIGO 키 확인 필요"


@dataclass(frozen=True)
class AigoConfig:
    api_url: str
    api_key: str


class UploadDeferred(Exception):
    """지금은 못 올림(인터넷, 서버 일시 오류, 하루 한도). retry_at이 없으면 호출 측이 간격을 정한다."""

    def __init__(self, message: str, retry_at: datetime | None = None):
        super().__init__(message)
        self.retry_at = retry_at


class UploadRejected(Exception):
    """다시 시도해도 안 됨. auth=True면 키 문제."""

    def __init__(self, message: str, auth: bool = False):
        super().__init__(message)
        self.auth = auth


def load_aigo_config(path: Path = DEFAULT_AIGO_CONFIG, environ: Mapping[str, str] = os.environ) -> AigoConfig | None:
    values = _read_env_file(path)
    values.update({key: value for key, value in environ.items() if key.startswith("DASHPI_AIGO_")})
    api_key = values.get("DASHPI_AIGO_API_KEY", "").strip()
    if not api_key:
        return None
    if any(ord(char) < 32 or ord(char) == 127 for char in api_key):
        log.warning("AIGO 키 형식 오류 — 업로드를 끕니다")
        return None
    try:
        api_url = _valid_base_url(values.get("DASHPI_AIGO_API_URL", "").strip())
    except AnalysisError:
        log.warning("AIGO 주소는 https여야 합니다 — 업로드를 끕니다")
        return None
    return AigoConfig(api_url, api_key)


def next_day_0005(now: datetime) -> datetime:
    return datetime.combine(now.date() + timedelta(days=1), time(0, 5), tzinfo=now.tzinfo)


class AigoClient:
    def __init__(self, config: AigoConfig, opener=None, timeout: float = 60.0):
        self.config, self.timeout = config, timeout
        self.opener = opener or urllib.request.build_opener(_NoRedirect())

    def upload(self, clip: Path) -> int:
        """생성 → presigned PUT → 제출. 분석 id를 돌려준다."""
        size = clip.stat().st_size
        ticket = self._api("POST", "/api/v1/analyses", {"filename": clip.name, "size": size, "consent": True})
        try:
            analysis_id, url, headers = int(ticket["id"]), str(ticket["upload_url"]), dict(ticket["upload_headers"])
        except (KeyError, TypeError, ValueError) as error:
            raise UploadDeferred("AIGO 응답 형식 오류") from error
        with clip.open("rb") as body:
            request = urllib.request.Request(url, data=body, method="PUT",
                                             headers={**headers, "Content-Length": str(size)})
            # presigned URL이 만료(403)되면 다음 시도에서 새로 만든다. 키는 보내지 않는다.
            self._send(request, put=True)
        self._api("POST", f"/api/v1/analyses/{analysis_id}/submit", None)
        return analysis_id

    def _api(self, method: str, path: str, payload: dict | None) -> dict:
        request = urllib.request.Request(
            self.config.api_url + path, method=method,
            data=json.dumps(payload).encode() if payload is not None else b"",
            headers={"Authorization": f"Bearer {self.config.api_key}", "Content-Type": "application/json"},
        )
        return self._send(request)

    def _send(self, request: urllib.request.Request, put: bool = False) -> dict:
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            raise self._http_error(error, put) from error
        except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError) as error:
            raise UploadDeferred("인터넷 연결 없음") from error
        try:
            return json.loads(raw) if raw else {}
        except ValueError:
            return {}

    @staticmethod
    def _http_error(error: urllib.error.HTTPError, put: bool) -> Exception:
        status = error.code
        if put or status == 408 or status >= 500:
            return UploadDeferred(f"AIGO 일시 오류 (HTTP {status})")
        if status == 429:
            return UploadDeferred("AIGO 하루 한도 도달", retry_at=next_day_0005(datetime.now().astimezone()))
        if status in (401, 403):
            return UploadRejected(AUTH_REASON, auth=True)
        try:
            message = json.loads(error.read()).get("message")
        except (ValueError, AttributeError, OSError):
            message = None
        return UploadRejected(message if isinstance(message, str) and message else f"AIGO 업로드 거부 (HTTP {status})")
