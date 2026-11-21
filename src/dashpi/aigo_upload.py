"""사고 클립을 AIGO 서버에 올린다. 설정이 있을 때만 켜지고, Pi 로컬 분석과 따로 돈다."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
import hashlib
import http.client
import json
import logging
import os
from pathlib import Path
import urllib.error
import urllib.request

from dashpi.ai_client import AnalysisError, _NoRedirect, _read_env_file, _valid_base_url, retry_delay
from dashpi.storage import IncidentStore, atomic_write, sha256_file

log = logging.getLogger("dashpi")

DEFAULT_AIGO_CONFIG = Path.home() / ".config" / "dashpi" / "aigo.env"
AUTH_REASON = "AIGO 키 확인 필요"
AIGO_STATE = "aigo.json"  # metadata.json과 따로 둔다. Pi 분석 스레드와 서로 덮어쓰지 않게.


@dataclass(frozen=True)
class AigoConfig:
    api_url: str
    api_key: str


class UploadDeferred(Exception):
    """지금은 못 올림(인터넷, 서버 일시 오류, 하루 한도). retry_at이 없으면 호출 측이 간격을 정한다."""

    def __init__(self, message: str, retry_at: datetime | None = None):
        super().__init__(message)
        self.retry_at = retry_at


class UploadRestart(Exception):
    """서버가 업로드를 받지 못했다(제출 409). 분석을 새로 만들어 다시 올린다."""


@dataclass(frozen=True)
class Ticket:
    analysis_id: int
    upload_url: str
    upload_headers: dict


class UploadRejected(Exception):
    """다시 시도해도 안 됨. auth=True면 키 문제."""

    def __init__(self, message: str, auth: bool = False):
        super().__init__(message)
        self.auth = auth


def load_aigo_configs(path: Path = DEFAULT_AIGO_CONFIG, environ: Mapping[str, str] = os.environ) -> list[AigoConfig]:
    """DASHPI_AIGO_API_KEY에 쉼표로 여러 키를 넣으면 계정마다 같은 클립을 올린다. 첫 키가 화면 표시 기준."""
    values = _read_env_file(path)
    values.update({key: value for key, value in environ.items() if key.startswith("DASHPI_AIGO_")})
    keys = [key.strip() for key in values.get("DASHPI_AIGO_API_KEY", "").split(",") if key.strip()]
    if not keys:
        return []
    if any(ord(char) < 32 or ord(char) == 127 for key in keys for char in key):
        log.warning("AIGO 키 형식 오류 — 업로드를 끕니다")
        return []
    try:
        api_url = _valid_base_url(values.get("DASHPI_AIGO_API_URL", "").strip())
    except AnalysisError:
        log.warning("AIGO 주소는 https여야 합니다 — 업로드를 끕니다")
        return []
    return [AigoConfig(api_url, key) for key in dict.fromkeys(keys)]


def load_aigo_config(path: Path = DEFAULT_AIGO_CONFIG, environ: Mapping[str, str] = os.environ) -> AigoConfig | None:
    configs = load_aigo_configs(path, environ)
    return configs[0] if configs else None


def state_name(index: int, api_key: str) -> str:
    """첫 키는 기존 aigo.json을 그대로 쓴다. 나머지는 키 지문으로 이름을 붙여 순서가 바뀌어도 섞이지 않게 한다."""
    return AIGO_STATE if index == 0 else f"aigo-{hashlib.sha256(api_key.encode()).hexdigest()[:12]}.json"


def next_day_0005(now: datetime) -> datetime:
    return datetime.combine(now.date() + timedelta(days=1), time(0, 5), tzinfo=now.tzinfo)


class AigoClient:
    def __init__(self, config: AigoConfig, opener=None, timeout: float = 60.0):
        self.config, self.timeout = config, timeout
        self.opener = opener or urllib.request.build_opener(_NoRedirect())

    # 생성 → presigned PUT → 제출. 단계를 나눠 두어, 제출만 실패하면 같은 분석을 다시 제출한다.
    def create(self, clip: Path) -> Ticket:
        ticket = self._api("POST", "/api/v1/analyses",
                           {"filename": clip.name, "size": clip.stat().st_size, "consent": True})
        try:
            return Ticket(int(ticket["id"]), str(ticket["upload_url"]), dict(ticket["upload_headers"]))
        except (KeyError, TypeError, ValueError) as error:
            raise UploadDeferred("AIGO 응답 형식 오류") from error

    def put(self, clip: Path, ticket: Ticket) -> None:
        with clip.open("rb") as body:
            request = urllib.request.Request(
                ticket.upload_url, data=body, method="PUT",
                headers={**ticket.upload_headers, "Content-Length": str(clip.stat().st_size)})
            self._send(request, put=True)  # 저장소 주소에는 키를 보내지 않는다

    def submit(self, analysis_id: int) -> None:
        self._api("POST", f"/api/v1/analyses/{analysis_id}/submit", None)

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
        if status == 408 or status >= 500:
            return UploadDeferred(f"AIGO 일시 오류 (HTTP {status})")
        if status == 429:
            return UploadDeferred("AIGO 하루 한도 도달", retry_at=next_day_0005(datetime.now().astimezone()))
        if put:  # 저장소의 4xx는 키 문제가 아니고, 다시 해도 같다
            return UploadRejected(f"AIGO 저장소 업로드 거부 (HTTP {status})")
        if status == 409:
            return UploadRestart("AIGO가 업로드를 받지 못함")
        if status in (401, 403):
            return UploadRejected(AUTH_REASON, auth=True)
        try:
            message = json.loads(error.read()).get("message")
        except (ValueError, AttributeError, OSError):
            message = None
        return UploadRejected(message if isinstance(message, str) and message else f"AIGO 업로드 거부 (HTTP {status})")


def read_state(store: IncidentStore, incident_id: str, name: str = AIGO_STATE) -> dict | None:
    try:
        state = json.loads((store.directory(incident_id) / name).read_text())
    except (FileNotFoundError, KeyError, OSError, ValueError):
        return None
    return state if isinstance(state, dict) else None


def _write_state(store: IncidentStore, incident_id: str, state: dict, name: str = AIGO_STATE) -> None:
    atomic_write(store.directory(incident_id) / name, json.dumps(state, sort_keys=True).encode())


def mark_pending(store: IncidentStore, incident_id: str, name: str = AIGO_STATE) -> None:
    """클립 저장 직후 부른다. 이미 상태 파일이 있으면 그대로 둔다."""
    if read_state(store, incident_id, name) is None:
        _write_state(store, incident_id, {"state": "pending", "attempts": 0}, name)


class AigoUploader:
    """aigo.json이 pending인 사고를 하나씩 올린다. 분석 worker와 별도 스레드."""

    def __init__(self, store: IncidentStore, client: AigoClient,
                 now: Callable[[], datetime] = lambda: datetime.now(UTC), state_name: str = AIGO_STATE):
        self.store, self.client, self.now, self.state_name = store, client, now, state_name
        self.running: Future | None = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dashpi-aigo")

    def _read(self, incident_id: str) -> dict | None:
        return read_state(self.store, incident_id, self.state_name)

    def _write(self, incident_id: str, state: dict) -> None:
        _write_state(self.store, incident_id, state, self.state_name)

    def mark_pending(self, incident_id: str) -> None:
        mark_pending(self.store, incident_id, self.state_name)

    def _ids(self) -> list[str]:
        try:
            return os.listdir(self.store.root / "incidents")
        except OSError:
            return []

    def recover(self) -> None:
        """키 문제로 실패한 업로드를 앱 시작 때 한 번 다시 대기시킨다(키를 고친 뒤 재시작하면 올라간다)."""
        for incident_id in self._ids():
            state = self._read(incident_id)
            if state and state.get("state") == "failed" and state.get("reason") == AUTH_REASON:
                self._write(incident_id, {"state": "pending", "attempts": 0})

    def tick(self) -> str | None:
        if self.running is not None and not self.running.done():
            return None
        now = self.now()
        due = []
        for incident_id in self._ids():
            state = self._read(incident_id)
            if not state or state.get("state") != "pending":
                continue
            try:
                when = datetime.fromisoformat(state["next_attempt_at"]) if state.get("next_attempt_at") else None
            except (TypeError, ValueError):
                when = None
            if when is None or when <= now:
                due.append((when or datetime.min.replace(tzinfo=UTC), incident_id))
        if not due:
            return None
        _, incident_id = min(due)
        self.running = self._executor.submit(self._upload, incident_id)
        return incident_id

    def _upload(self, incident_id: str) -> None:
        state = self._read(incident_id) or {"attempts": 0}
        try:
            incident = self.store.load(incident_id)
        except (FileNotFoundError, KeyError, OSError, ValueError):
            log.warning("AIGO 업로드 대상 사고를 찾을 수 없음: %s", incident_id)
            self._write(incident_id, {**state, "state": "failed", "reason": "사고 기록 없음"})
            return
        clip = self.store.directory(incident_id) / "clip.mp4"
        try:
            ok = incident.clip is not None and sha256_file(clip) == incident.clip.sha256
        except OSError:
            ok = False
        if not ok:
            self._write(incident_id, {**state, "state": "failed", "reason": "클립 확인 실패"})
            return
        now = self.now()
        try:
            if state.get("phase") == "put" and state.get("analysis_id"):
                analysis_id = int(state["analysis_id"])  # 지난번에 올려 둔 영상을 제출만 다시 한다
            else:
                ticket = self.client.create(clip)
                analysis_id = ticket.analysis_id
                self.client.put(clip, ticket)
                state = {**state, "analysis_id": analysis_id, "phase": "put"}
                self._write(incident_id, {**state, "state": "pending"})
            self.client.submit(analysis_id)
        except UploadRestart as error:
            state = {key: value for key, value in state.items() if key not in ("analysis_id", "phase")}
            self._write(incident_id, {**state, "state": "pending", "next_attempt_at": None,
                                                   "reason": str(error)})
            log.info("AIGO 업로드 다시 시작: %s", incident_id)
        except UploadDeferred as error:
            attempts = int(state.get("attempts", 0)) + 1
            retry_at = error.retry_at or now + retry_delay(attempts)
            self._write(incident_id, {**state, "state": "pending", "attempts": attempts,
                                                   "next_attempt_at": retry_at.isoformat(), "reason": str(error)})
            log.info("AIGO 업로드 대기: %s (%s)", incident_id, error)
        except UploadRejected as error:
            self._write(incident_id, {**state, "state": "failed", "reason": str(error)})
            log.warning("AIGO 업로드 실패: %s (%s)", incident_id, error)
        except Exception as error:  # 예상 못 한 오류도 사고 기록을 건드리지 않고 다음에 다시 시도한다
            log.exception("AIGO 업로드 오류: %s", incident_id)
            attempts = int(state.get("attempts", 0)) + 1
            self._write(incident_id, {**state, "state": "pending", "attempts": attempts,
                                                   "next_attempt_at": (now + retry_delay(attempts)).isoformat(),
                                                   "reason": type(error).__name__})
        else:
            self._write(incident_id, {"state": "uploaded", "analysis_id": analysis_id,
                                                   "uploaded_at": now.isoformat()})
            log.info("AIGO 업로드 완료: %s → 분석 #%s", incident_id, analysis_id)

    def close(self) -> None:
        # 종료 때 화면을 붙잡지 않는다. 진행 중인 업로드는 다음 실행에서 이어서 한다.
        self._executor.shutdown(wait=False, cancel_futures=True)


class AigoUploaders:
    """계정(키)마다 업로더 하나. 화면과 타이머는 이 묶음 하나만 본다."""

    def __init__(self, uploaders: list[AigoUploader]):
        self.uploaders = uploaders

    def mark_pending(self, incident_id: str) -> None:
        for uploader in self.uploaders:
            uploader.mark_pending(incident_id)

    def recover(self) -> None:
        for uploader in self.uploaders:
            uploader.recover()

    def tick(self) -> None:
        for uploader in self.uploaders:
            try:
                uploader.tick()
            except Exception:  # 한 계정이 막혀도 나머지는 올린다
                log.exception("AIGO 업로드 확인 실패")

    def close(self) -> None:
        for uploader in self.uploaders:
            uploader.close()


def build_uploaders(store: IncidentStore, configs: list[AigoConfig]) -> AigoUploaders | None:
    if not configs:
        return None
    return AigoUploaders([AigoUploader(store, AigoClient(config), state_name=state_name(index, config.api_key))
                          for index, config in enumerate(configs)])
