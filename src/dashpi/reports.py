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

    def analyze(self, frames: list[tuple[Path, float]]) -> dict:
        images = [base64.b64encode(path.read_bytes()).decode() for path, _timestamp in frames]
        body = json.dumps(
            {
                "model": self.model,
                "stream": False,
                "format": "json",
                "prompt": "Return JSON with incident_timestamp (seconds from first frame), summary, observations, and limitations. Describe evidence only; do not determine legal fault."
                "\nThe first frame means the evidence clip origin (0 seconds). Image timestamps in image order, in seconds from that origin: "
                + json.dumps([timestamp for _path, timestamp in frames])
                + ". Use this clip-relative timebase for all timestamps.",
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


def render_report_html(report: dict, video_bytes: bytes, keyframe_bytes: list[bytes]) -> str:
    if len(keyframe_bytes) != 3:
        raise ValueError("report requires three key frames")
    incident_time = float(report["incident_timestamp"])
    transfer_start = float(report["transfer_window"]["start"])
    transfer_end = float(report["transfer_window"]["end"])
    marker_percent = min(
        100.0,
        max(
            0.0,
            (incident_time - transfer_start) / (transfer_end - transfer_start) * 100.0,
        ),
    )
    tracks: dict[str, set[int]] = {}
    for item in report["object_observations"]:
        tracks.setdefault(str(item["label"]), set()).add(int(item["track_id"]))
    track_count = len({track for values in tracks.values() for track in values})
    largest_count = max((len(values) for values in tracks.values()), default=1)
    object_chart = "".join(
        f'<div><span>{html.escape(label)}</span><i style="width:{len(values) / largest_count * 100:.2f}%"></i><b>{len(values)}</b></div>'
        for label, values in sorted(tracks.items())
    ) or "<p>추적된 객체 없음</p>"
    object_rows = "".join(
        f'<tr><td>{float(item["timestamp"]):.2f}s</td><td>{html.escape(str(item["label"]))} #{int(item["track_id"])}</td><td>{float(item["confidence"]):.0%}</td></tr>'
        for item in report["object_observations"]
    )
    observation_markup = "".join(
        f'<li>{float(item["timestamp"]):.1f}s — {html.escape(str(item["description"]))}</li>'
        for item in report["observations"]
    )
    analysis_markup = f'<p>{html.escape(str(report["summary"]))}</p><ol>{observation_markup}</ol>'
    warning_markup = "<p>AI output is advisory and may be incomplete.</p>" + "".join(
        f"<p>{html.escape(str(value))}</p>"
        for value in [*report["limitations"], *report["warnings"]]
    )
    digest_markup = "".join(
        f"<p><code>{html.escape(name)}</code> {html.escape(str(digest))}</p>"
        for name, digest in sorted(report["digests"].items())
    )
    provenance_markup = (
        f'<p>Incident: {html.escape(str(report["incident_id"]))}</p>'
        f'<p>Triggered: {html.escape(str(report["triggered_at"]))}</p>'
        f'<p>Model: {html.escape(str(report["model"]))}</p>'
        f'<p>Generated: {html.escape(str(report["generated_at"]))}</p>'
        f'<p>Optional overlays: {html.escape(json.dumps(report["overlays"], sort_keys=True))}</p>'
    )
    video_source = "data:video/mp4;base64," + base64.b64encode(video_bytes).decode("ascii")
    frame_sources = [
        "data:image/jpeg;base64," + base64.b64encode(value).decode("ascii")
        for value in keyframe_bytes
    ]
    cards = (
        f'<article class="card"><span>사고 시점</span><b>{incident_time:.1f}s</b></article>'
        f'<article class="card"><span>전송 구간</span><b>{transfer_start:.1f}–{transfer_end:.1f}s</b></article>'
        f'<article class="card"><span>추적 객체</span><b>{track_count}</b></article>'
    )
    keyframes = "".join(
        f'<figure><img src="{source}" alt="{label}"><figcaption>{label}</figcaption></figure>'
        for source, label in zip(
            frame_sources, ("사고 전", "사고 순간", "사고 후"), strict=True
        )
    )
    return f'''<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DashPi 사고 분석 리포트</title><style>
:root{{color-scheme:dark;--bg:#09111f;--panel:#111d31;--line:#29405f;--text:#f5f7fb;--muted:#9fb0c7;--accent:#55a7ff;--danger:#ff5d68}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:15px/1.55 system-ui,sans-serif}}main{{max-width:1080px;margin:auto;padding:24px}}
.cards,.keyframes,.object-chart{{display:grid;gap:12px}}.cards{{grid-template-columns:repeat(3,1fr)}}.card,section{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px}}.keyframes{{grid-template-columns:repeat(3,1fr)}}img,video{{width:100%;border-radius:10px}}.incident-timeline{{position:relative;height:10px;background:#24344d;border-radius:9px}}.incident-timeline i{{position:absolute;top:-5px;width:3px;height:20px;background:var(--danger)}}.object-chart>div{{display:grid;grid-template-columns:100px 1fr 32px;align-items:center;gap:8px}}.object-chart>div i{{display:block;height:10px;background:var(--accent);border-radius:8px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:7px;border-bottom:1px solid var(--line);text-align:left}}
@media(max-width:700px){{.cards,.keyframes{{grid-template-columns:1fr}}}}
@media print{{body{{background:white;color:black}}.screen-only{{display:none!important}}section,.card{{border:1px solid #bbb;break-inside:avoid}}.keyframes{{grid-template-columns:repeat(3,1fr)}}}}
</style></head><body><main>
<header><p>DashPi · 검증된 오프라인 리포트</p><h1>사고 분석 리포트</h1></header>
<section class="screen-only"><video controls preload="metadata" src="{video_source}"></video></section>
<section class="cards">{cards}</section>
<section><h2>10초 타임라인</h2><div class="incident-timeline"><i style="left:{marker_percent:.2f}%"></i></div></section>
<section class="object-chart"><h2>객체 통계</h2>{object_chart}<table><thead><tr><th>시점</th><th>객체</th><th>신뢰도</th></tr></thead><tbody>{object_rows}</tbody></table></section>
<section class="keyframes">{keyframes}</section>
<section><h2>분석</h2>{analysis_markup}<h2>한계와 경고</h2>{warning_markup}<h2>생성 정보</h2>{provenance_markup}<h2>SHA-256</h2>{digest_markup}</section>
<nav class="screen-only"><button type="button" onclick="downloadReport()">Download HTML</button><button type="button" onclick="window.print()">Save as PDF</button></nav>
</main><script>
function downloadReport(){{const blob=new Blob(['<!doctype html>'+document.documentElement.outerHTML],{{type:'text/html'}});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='report.html';a.click();setTimeout(()=>URL.revokeObjectURL(url),0)}}
</script></body></html>'''
