import base64
import html
import json
import urllib.request
from pathlib import Path


class OllamaClient:
    def __init__(
        self,
        model: str,
        base_url: str = "http://127.0.0.1:11434",
        timeout: float = 120.0,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def validate_model(self) -> None:
        with urllib.request.urlopen(self.base_url + "/api/tags", timeout=5.0) as response:
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
                "prompt": "Describe visible events by timestamp. Return summary, observations, limitations.",
                "images": images,
            }
        ).encode()
        request = urllib.request.Request(
            self.base_url + "/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(json.loads(response.read())["response"])


def validate_report(raw: dict, clip_sha256: str, model: str, generated_at: str) -> dict:
    if (
        not isinstance(raw.get("summary"), str)
        or not isinstance(raw.get("observations"), list)
        or not isinstance(raw.get("limitations"), list)
    ):
        raise ValueError("invalid report shape")
    if any(
        not isinstance(item, dict)
        or not isinstance(item.get("timestamp"), (int, float))
        or not isinstance(item.get("description"), str)
        for item in raw["observations"]
    ):
        raise ValueError("invalid observation")
    if any(not isinstance(item, str) for item in raw["limitations"]):
        raise ValueError("invalid limitation")
    return {
        **raw,
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
        f"<h2>Observations</h2><ul>{observations}</ul>"
        f"<h2>Limitations</h2><ul>{limitations}</ul></main>"
    )
