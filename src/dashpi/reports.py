import base64
import html
import json
import math


NEGLIGENCE_ITEMS = (
    ("signal", "신호 지시 관련 장면"),
    ("center_line", "중앙선 관련 장면"),
    ("speeding", "제한속도 초과 여부"),
    ("overtaking", "앞지르기·끼어들기 관련 장면"),
    ("railroad_crossing", "철길건널목 관련 장면"),
    ("crosswalk", "횡단보도 보행자 관련 장면"),
    ("unlicensed", "운전면허 상태"),
    ("intoxication", "음주·약물 상태"),
    ("sidewalk", "보도 침범 관련 장면"),
    ("passenger_fall", "승객 추락 방지 관련 장면"),
    ("school_zone", "어린이보호구역 관련 장면"),
    ("cargo", "화물 고정 관련 장면"),
)
NEGLIGENCE_STATUSES = {"observed", "not_observed", "not_determinable"}
NONVISUAL_REVIEW_KEYS = {"speeding", "unlicensed", "intoxication"}


def _unavailable_review() -> dict:
    return {
        key: {
            "status": "not_determinable",
            "evidence": "카메라 영상만으로 확인할 수 없습니다.",
            "timestamp": None,
        }
        for key, _label in NEGLIGENCE_ITEMS
    }


def _validate_review(raw: object, clip_duration: float) -> dict:
    if raw is None:
        return _unavailable_review()
    keys = {key for key, _label in NEGLIGENCE_ITEMS}
    if not isinstance(raw, dict) or set(raw) != keys:
        raise ValueError("invalid major negligence review")
    result = {}
    for key, _label in NEGLIGENCE_ITEMS:
        item = raw[key]
        if (
            not isinstance(item, dict)
            or set(item) != {"status", "evidence", "timestamp"}
            or item["status"] not in NEGLIGENCE_STATUSES
            or not isinstance(item["evidence"], str)
        ):
            raise ValueError("invalid major negligence review")
        timestamp = item["timestamp"]
        if timestamp is not None and (
            isinstance(timestamp, bool)
            or not isinstance(timestamp, (int, float))
            or not math.isfinite(timestamp)
            or not 0.0 <= timestamp <= clip_duration
        ):
            raise ValueError("invalid major negligence review")
        result[key] = {
            "status": item["status"],
            "evidence": item["evidence"],
            "timestamp": timestamp,
        }
    unavailable = _unavailable_review()
    for key in NONVISUAL_REVIEW_KEYS:
        result[key] = unavailable[key]
    return result


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
        or not set(raw) <= {
            "incident_timestamp", "summary", "observations", "limitations",
            "major_negligence_review",
        }
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
        "major_negligence_review": _validate_review(
            raw.get("major_negligence_review"), clip_duration
        ),
        "source_clip_sha256": clip_sha256,
        "model": model,
        "generated_at": generated_at,
    }


def render_report_html(report: dict, video_bytes: bytes, keyframe_bytes: list[bytes]) -> str:
    if len(keyframe_bytes) != 3:
        raise ValueError("report requires three key frames")
    incident_time = float(report["incident_timestamp"])
    tracks: dict[str, set[int]] = {}
    for item in report["object_observations"]:
        tracks.setdefault(str(item["label"]), set()).add(int(item["track_id"]))
    largest_count = max((len(values) for values in tracks.values()), default=1)
    object_chart = "".join(
        f'<div><span>{html.escape(label)}</span><i style="width:{len(values) / largest_count * 100:.2f}%"></i><b>{len(values)}</b></div>'
        for label, values in sorted(tracks.items())
    ) or "<p>추적된 객체 없음</p>"
    object_rows = "".join(
        f'<tr><td>{float(item["timestamp"]):.2f}s</td><td>{html.escape(str(item["label"]))} #{int(item["track_id"])}</td><td>{float(item["confidence"]):.0%}</td></tr>'
        for item in report["object_observations"]
    )

    def relative_time(timestamp: float) -> str:
        offset = timestamp - incident_time
        return "0.0초" if abs(offset) < 0.05 else f"{offset:+.1f}초"

    observation_markup = "".join(
        '<li><time>' + relative_time(float(item["timestamp"])) + '</time><span>'
        + html.escape(str(item["description"])) + '</span></li>'
        for item in report["observations"]
    ) or "<li><span>표시할 시간별 관찰이 없습니다.</span></li>"
    warning_markup = "<p>AI output is advisory and may be incomplete.</p>" + "".join(
        f"<p>{html.escape(str(value))}</p>"
        for value in [*report["limitations"], *report["warnings"]]
    )
    status_labels = {
        "observed": "영상에서 관련 장면 관찰됨",
        "not_observed": "영상에서 관련 장면 관찰되지 않음",
        "not_determinable": "영상만으로 확인 불가",
    }
    review = report.get("major_negligence_review") or _unavailable_review()
    review_markup = "".join(
        '<li><div><b>' + html.escape(label) + '</b><span class="review-status">'
        + html.escape(status_labels.get(str(review[key]["status"]), "영상만으로 확인 불가"))
        + '</span></div><p>' + html.escape(str(review[key]["evidence"]))
        + (f' · {relative_time(float(review[key]["timestamp"]))}' if review[key]["timestamp"] is not None else '')
        + '</p></li>'
        for key, label in NEGLIGENCE_ITEMS
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
    keyframes = "".join(
        f'<figure><img src="{source}" alt="{label}"><figcaption>{label}</figcaption></figure>'
        for source, label in zip(
            frame_sources, ("사고 전", "사고 순간", "사고 후"), strict=True
        )
    )
    return f'''<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DashPi 사고 분석 리포트</title><style>
:root{{color-scheme:light;--bg:#eef2f7;--panel:#fff;--line:#dce3ec;--text:#142033;--muted:#657187;--accent:#165dff;--soft:#edf3ff;--warn:#fff7df}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:15px/1.6 system-ui,sans-serif}}main{{max-width:760px;margin:auto;padding:20px}}
header{{padding:8px 4px 14px}}header p{{margin:0;color:var(--muted)}}h1{{margin:4px 0 2px;font-size:28px}}h2{{margin:0 0 10px;font-size:18px}}section,details{{margin:0 0 12px;background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:16px}}summary{{cursor:pointer;font-size:18px;font-weight:700}}img,video{{width:100%;border-radius:12px}}.keyframes{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}}figure{{margin:0}}figcaption{{margin-top:5px;text-align:center;color:var(--muted);font-size:12px}}.summary{{border-left:4px solid var(--accent)}}.timeline{{list-style:none;margin:0;padding:0}}.timeline li{{display:grid;grid-template-columns:64px 1fr;gap:10px;padding:8px 0;border-bottom:1px solid var(--line)}}.timeline time{{color:var(--accent);font-weight:800}}.limitations{{background:var(--warn)}}.review{{list-style:none;margin:14px 0 0;padding:0}}.review li{{padding:10px 0;border-top:1px solid var(--line)}}.review li div{{display:flex;justify-content:space-between;gap:12px}}.review li p{{margin:4px 0 0;color:var(--muted)}}.review-status{{color:var(--accent);font-size:12px;font-weight:700;text-align:right}}.emergency-grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}.emergency-grid p{{margin:0;padding:12px;border-radius:12px;background:var(--soft);text-align:center;font-size:17px;font-weight:800}}.object-chart{{display:grid;gap:8px;margin:12px 0}}.object-chart>div{{display:grid;grid-template-columns:100px 1fr 32px;align-items:center;gap:8px}}.object-chart>div i{{display:block;height:10px;background:var(--accent);border-radius:8px}}.incident-timeline{{height:4px;margin:10px 0;background:var(--accent);border-radius:4px}}table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{padding:7px;border-bottom:1px solid var(--line);text-align:left}}code{{overflow-wrap:anywhere}}nav{{display:flex;gap:8px}}button{{padding:10px 12px;border:0;border-radius:10px;background:var(--accent);color:#fff;font-weight:700}}
@media(max-width:520px){{main{{padding:12px}}.keyframes{{gap:5px}}.timeline li{{grid-template-columns:58px 1fr}}.review li div{{display:block}}.review-status{{display:block;text-align:left}}}}
@media print{{body{{background:white;color:black}}.screen-only{{display:none!important}}section,details{{border:1px solid #bbb;break-inside:avoid}}.keyframes{{grid-template-columns:repeat(3,1fr)}}details{{display:block}}}}
</style></head><body><main>
<header><p>DashPi · SHA-256 무결성 검증 완료</p><h1>사고 분석 리포트</h1><p>{html.escape(str(report["triggered_at"]))}</p></header>
<section class="screen-only" data-section="video"><video controls preload="metadata" src="{video_source}"></video></section>
<section class="keyframes" data-section="keyframes">{keyframes}</section>
<section class="summary" data-section="summary"><h2>AI 핵심 요약</h2><p>{html.escape(str(report["summary"]))}</p></section>
<section data-section="timeline"><h2>사실 타임라인</h2><div class="incident-timeline"></div><ol class="timeline">{observation_markup}</ol></section>
<section class="limitations" data-section="limitations"><h2>확인할 수 없는 내용</h2><p>45초 전체의 표본 프레임과 사고 주변 프레임을 분석했습니다. GPS, 실제 속도와 충격량은 측정되지 않았습니다.</p>{warning_markup}</section>
<details data-section="major-negligence"><summary>12대 중과실 관련 확인 항목</summary><p>법적 판정이 아닌 영상 사실 정리입니다.</p><ul class="review">{review_markup}</ul></details>
<section data-section="emergency"><h2>긴급 번호</h2><div class="emergency-grid"><p>119 · 구급/소방</p><p>112 · 경찰</p></div></section>
<details data-section="evidence"><summary>증거 상세</summary>{provenance_markup}<h2>객체 추적</h2><div class="object-chart">{object_chart}</div><table><thead><tr><th>시점</th><th>객체</th><th>신뢰도</th></tr></thead><tbody>{object_rows}</tbody></table><h2>SHA-256</h2>{digest_markup}</details>
<nav class="screen-only"><button type="button" onclick="downloadReport()">Download HTML</button><button type="button" onclick="window.print()">Save as PDF</button></nav>
</main><script>
function downloadReport(){{const blob=new Blob(['<!doctype html>'+document.documentElement.outerHTML],{{type:'text/html'}});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='report.html';a.click();setTimeout(()=>URL.revokeObjectURL(url),0)}}
</script></body></html>'''
