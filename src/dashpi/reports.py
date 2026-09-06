import base64
import html
import ipaddress
import json
import math
import urllib.parse
import urllib.request
from pathlib import Path


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def _validated_loopback_origin(base_url: str) -> str:
    parsed = urllib.parse.urlsplit(base_url)
    try:
        valid = (
            parsed.scheme == "http"
            and parsed.hostname is not None
            and ipaddress.ip_address(parsed.hostname).is_loopback
            and parsed.username is None
            and parsed.password is None
            and parsed.path in ("", "/")
            and not parsed.query
            and not parsed.fragment
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("base_url must be a numeric loopback HTTP origin")
    return base_url.rstrip("/")


class OllamaClient:
    def __init__(
        self,
        model: str,
        base_url: str = "http://127.0.0.1:11434",
        timeout: float = 120.0,
    ):
        self.model = model
        self.base_url = _validated_loopback_origin(base_url)
        self.timeout = timeout
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), _NoRedirect()
        )

    def validate_model(self) -> None:
        with self.opener.open(self.base_url + "/api/tags", timeout=5.0) as response:
            names = {item["name"] for item in json.loads(response.read())["models"]}
        if self.model not in names:
            raise ValueError(f"Ollama model not installed: {self.model}")

    def analyze(self, frames: list[Path]) -> dict:
        images = [base64.b64encode(path.read_bytes()).decode() for path in frames]
        body = json.dumps(
            {
                "model": self.model,
                "stream": False,
                "format": "json",
                "prompt": "Return JSON with incident_timestamp (seconds from first frame), summary, observations, and limitations. Describe evidence only; do not determine legal fault.",
                "images": images,
            }
        ).encode()
        request = urllib.request.Request(
            self.base_url + "/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with self.opener.open(request, timeout=self.timeout) as response:
            return json.loads(json.loads(response.read())["response"])


def validate_report(
    raw: object,
    clip_sha256: str,
    model: str,
    generated_at: str,
    clip_duration: float,
    incident_offset_override: float | None = None,
) -> dict:
    if (
        not isinstance(raw, dict)
        or not {"summary", "observations", "limitations"} <= set(raw)
        or not set(raw) <= {"incident_timestamp", "summary", "observations", "limitations"}
        or not isinstance(raw["summary"], str)
        or not isinstance(raw["observations"], list)
        or not isinstance(raw["limitations"], list)
    ):
        raise ValueError("invalid report shape")
    if any(
        not isinstance(item, dict)
        or set(item) != {"timestamp", "description"}
        or isinstance(item["timestamp"], bool)
        or not isinstance(item["timestamp"], (int, float))
        or not math.isfinite(item["timestamp"])
        or not isinstance(item["description"], str)
        for item in raw["observations"]
    ):
        raise ValueError("invalid observation")
    if any(not isinstance(item, str) for item in raw["limitations"]):
        raise ValueError("invalid limitation")
    incident_timestamp = (
        raw.get("incident_timestamp")
        if incident_offset_override is None
        else incident_offset_override
    )
    if (
        isinstance(incident_timestamp, bool)
        or not isinstance(incident_timestamp, (int, float))
        or not math.isfinite(incident_timestamp)
        or not 0.0 <= incident_timestamp <= clip_duration
    ):
        raise ValueError("invalid incident timestamp")
    return {
        "incident_timestamp": incident_timestamp,
        "summary": raw["summary"],
        "observations": [
            {"timestamp": item["timestamp"], "description": item["description"]}
            for item in raw["observations"]
        ],
        "limitations": list(raw["limitations"]),
        "source_clip_sha256": clip_sha256,
        "model": model,
        "generated_at": generated_at,
    }


def render_report_html(report: dict) -> str:
    observations = "".join(
        f"<li>{float(item['timestamp']):.1f}s — {html.escape(str(item['description']))}</li>"
        for item in report["observations"]
    )
    limitations = "".join(f"<li>{html.escape(str(item))}</li>" for item in report["limitations"])
    return (
        "<main><h1>DashPi incident report</h1>"
        f"<p>{html.escape(report['summary'])}</p>"
        "<p>AI output is advisory and may be incomplete.</p>"
        f"<p>Source clip SHA-256: {html.escape(str(report['source_clip_sha256']))}</p>"
        f"<p>Model: {html.escape(str(report['model']))}</p>"
        f"<p>Generated at: {html.escape(str(report['generated_at']))}</p>"
        f"<h2>Observations</h2><ul>{observations}</ul>"
        f"<h2>Limitations</h2><ul>{limitations}</ul></main>"
    )
