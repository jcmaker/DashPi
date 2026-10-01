# Evidence-First Mobile Incident Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Analyze the full 45-second evidence window, produce a factual 12-item major-negligence review, and show a video-first mobile report before optional sharing or external saving.

**Architecture:** Keep the existing single self-contained HTML optical payload. The Pi combines full-window sample frames with dense incident-window frames, returns a strict structured review, and renders the selected B layout. The native receiver continues to verify and silently retain the payload, extracts the embedded video for native playback, shows the report immediately, and offers sharing below the preview.

**Tech Stack:** Python 3.11+, OpenCV/FFmpeg media helpers, OpenAI-compatible structured output, pytest, React Native/Expo, TypeScript, Node test runner, react-native-webview

## Global Constraints

- Analyze the 45-second clip using full-window uniform samples plus dense incident-window samples.
- Transfer only the 10-second derivative centered on the incident.
- Do not add GPS, CAN, IMU, audio, speed, impact-force, or legal-fault claims.
- Render `119 · 구급/소방` and `112 · 경찰` as plain text without `tel:` links or call actions.
- Label the 12-item section as video evidence review, never as a legal determination.
- Show the verified report before any user-triggered external download, file save, or share flow.
- Preserve DPQ1/DPC1, the single HTML payload, SHA-256 verification, and existing app-internal recovery storage.
- Add no dependencies.

---

## File Structure

- `src/dashpi/analysis.py` — combine full and dense samples; request structured timeline and review data.
- `src/dashpi/reports.py` — validate the new review and render the evidence-first HTML.
- `tests/test_analysis.py` — prove the observation call covers the full clip and enforces nonvisual items.
- `tests/test_reports.py` — prove strict review validation, B-layout order, escaping, and plain emergency numbers.
- `receiver-native/src/preview-model.ts` — remove the empty HTML video slot after lifting video into the native player.
- `receiver-native/tests/preview-model.test.ts` — prove native video appears before a nonblank HTML report and no report download control is required first.

---

### Task 1: Full-window factual AI output

**Files:**
- Modify: `src/dashpi/analysis.py`
- Modify: `src/dashpi/reports.py`
- Test: `tests/test_analysis.py`
- Test: `tests/test_reports.py`

**Interfaces:**
- Produces: `major_negligence_review: dict[str, {status: str, evidence: str, timestamp: float | None}]`.
- Produces: `merge_observation_frames(full, dense) -> list[tuple[Path, float]]` ordered by timestamp with dense duplicates preferred.
- Consumes: existing `Analyzer.__call__(frames, clip_path, frame_dir, incident_offset_override)`; no caller signature changes.

- [ ] **Step 1: Add failing report-validation tests**

Add a helper and tests to `tests/test_reports.py`:

```python
from dashpi.reports import NEGLIGENCE_ITEMS, validate_report


def review(status="not_observed"):
    return {
        key: {"status": status, "evidence": "관련 장면 없음", "timestamp": None}
        for key, _label in NEGLIGENCE_ITEMS
    }


def test_report_keeps_exactly_twelve_video_review_items():
    raw = {
        "incident_timestamp": 2.5,
        "summary": "차량이 정지했다.",
        "observations": [],
        "limitations": ["표본 프레임 분석"],
        "major_negligence_review": review(),
    }
    report = validate_report(raw, "0" * 64, "model", "now", 5.0)
    assert list(report["major_negligence_review"]) == [key for key, _ in NEGLIGENCE_ITEMS]
    assert len(report["major_negligence_review"]) == 12


def test_nonvisual_review_items_are_never_reported_as_observed():
    value = review("observed")
    raw = {
        "incident_timestamp": 2.5,
        "summary": "x",
        "observations": [],
        "limitations": [],
        "major_negligence_review": value,
    }
    report = validate_report(raw, "0" * 64, "model", "now", 5.0)
    for key in ("speeding", "unlicensed", "intoxication"):
        assert report["major_negligence_review"][key] == {
            "status": "not_determinable",
            "evidence": "카메라 영상만으로 확인할 수 없습니다.",
            "timestamp": None,
        }
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
pytest -q tests/test_reports.py -k 'twelve_video_review or nonvisual_review'
```

Expected: collection fails because `NEGLIGENCE_ITEMS` does not exist.

- [ ] **Step 3: Add the fixed review vocabulary and validation**

In `src/dashpi/reports.py`, define one shared ordered tuple:

```python
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
```

Extend `validate_report` to accept the optional `major_negligence_review` key. For legacy callers that omit it, create all 12 items with `not_determinable`. Reject unknown/missing review keys, unknown statuses, nonstring evidence, booleans, nonfinite timestamps, and timestamps outside the clip. Override the three `NONVISUAL_REVIEW_KEYS` with the exact value asserted above.

- [ ] **Step 4: Verify the validation tests pass**

Run:

```bash
pytest -q tests/test_reports.py -k 'twelve_video_review or nonvisual_review'
```

Expected: 2 passed.

- [ ] **Step 5: Add a failing 45-second observation test**

Import `NEGLIGENCE_ITEMS` beside `validate_report` in `tests/test_analysis.py`, add the following helper, and include its result in `ANSWERS["observe"]`:

```python
def review(status="not_observed"):
    return {
        key: {"status": status, "evidence": "관련 장면 없음", "timestamp": None}
        for key, _label in NEGLIGENCE_ITEMS
    }
```

Replace the incident-window-only assertion with:

```python
def test_observe_uses_full_clip_context_and_dense_incident_frames(tmp_path):
    clip = make_video(tmp_path / "clip.mp4", 8)
    client = ScriptedClient(ANSWERS)
    analyzer(tmp_path, client)(frames_for(clip, tmp_path), clip, tmp_path / "work")

    content = client.calls[1][2][1]["content"]
    stamps = [
        float(part["text"].removesuffix("초"))
        for part in content
        if part["type"] == "text" and part["text"].endswith("초")
    ]
    assert min(stamps) == pytest.approx(0.0, abs=0.1)
    assert max(stamps) == pytest.approx(8.0, abs=0.1)
    assert any(1.0 < stamp < 7.0 for stamp in stamps)
    assert len(stamps) > 12
```

Also assert the final analyzer result contains all 12 review keys.

- [ ] **Step 6: Run the analysis test and verify RED**

Run:

```bash
pytest -q tests/test_analysis.py::test_observe_uses_full_clip_context_and_dense_incident_frames
```

Expected: FAIL because the observation call currently receives only 12 dense incident-window frames.

- [ ] **Step 7: Implement combined frame observation and structured review output**

In `src/dashpi/analysis.py`:

- Import `NEGLIGENCE_ITEMS` from `dashpi.reports`.
- Add `major_negligence_review` to `OBSERVE_SCHEMA` as an object with exactly the 12 fixed keys. Each value requires `status`, `evidence`, and nullable `timestamp`; status is limited to `observed`, `not_observed`, or `not_determinable`.
- Update the observation instruction to state that the supplied frames cover the full clip plus a dense incident window; require visible facts only and explicitly forbid legal conclusions.
- Combine the original `frames` and new dense frames before `observe`. Deduplicate equal timestamps with the dense frame winning, then sort by timestamp.
- Return `major_negligence_review` beside `observations` from `Analyzer`.
- Make `FakeAnalyzer` return a complete 12-item `not_determinable` review.
- Keep `summarize` grounded only in timestamped observations.

The combination can remain a small helper:

```python
def merge_observation_frames(full, dense):
    by_time = {round(timestamp, 3): (path, timestamp) for path, timestamp in full}
    by_time.update({round(timestamp, 3): (path, timestamp) for path, timestamp in dense})
    return sorted(by_time.values(), key=lambda item: item[1])
```

- [ ] **Step 8: Run analysis and report tests**

Run:

```bash
pytest -q tests/test_analysis.py tests/test_reports.py
```

Expected: all tests pass.

- [ ] **Step 9: Commit Task 1**

```bash
git add docs/superpowers/specs/2026-10-02-evidence-first-mobile-report-design.md docs/superpowers/plans/2026-10-02-evidence-first-mobile-report.md src/dashpi/analysis.py src/dashpi/reports.py tests/test_analysis.py tests/test_reports.py
git commit -m "feat: analyze full incident context"
```

---

### Task 2: Evidence-first B-layout HTML

**Files:**
- Modify: `src/dashpi/reports.py`
- Test: `tests/test_reports.py`

**Interfaces:**
- Consumes: validated `major_negligence_review` from Task 1.
- Produces: the existing `render_report_html(report, video_bytes, keyframe_bytes) -> str`, with the same signature and self-contained output.

- [ ] **Step 1: Add a failing report-order and safety test**

Add to `tests/test_reports.py`:

```python
def test_mobile_report_is_video_first_and_requires_no_download_before_preview():
    report = complete_report_fixture()
    report["major_negligence_review"] = review()
    rendered = render_report_html(report, b"video", [b"before", b"moment", b"after"])

    markers = [
        'data-section="video"',
        'data-section="keyframes"',
        'data-section="summary"',
        'data-section="timeline"',
        'data-section="limitations"',
        'data-section="major-negligence"',
        'data-section="emergency"',
        'data-section="evidence"',
    ]
    positions = [rendered.index(marker) for marker in markers]
    assert positions == sorted(positions)
    assert "119 · 구급/소방" in rendered
    assert "112 · 경찰" in rendered
    assert "tel:" not in rendered
    assert "법적 판정이 아닌 영상 사실 정리입니다." in rendered
```

Add a second test proving hostile summary, evidence, and limitation text remain escaped in the new sections.

- [ ] **Step 2: Run the layout tests and verify RED**

Run:

```bash
pytest -q tests/test_reports.py -k 'mobile_report or escaped'
```

Expected: FAIL because the current HTML has no B-layout section markers or emergency-number block.

- [ ] **Step 3: Replace only the report markup and CSS needed for B layout**

Keep the current embedded data video, three data images, print support, hashes, model metadata, and HTML escaping. Reorder and relabel the document as follows:

```html
<header>사고 절대 시각 · 무결성 검증 완료</header>
<section class="video screen-only" data-section="video">…10초 video…</section>
<section class="keyframes" data-section="keyframes">…사고 전/순간/후…</section>
<section data-section="summary"><h2>AI 핵심 요약</h2>…</section>
<section data-section="timeline"><h2>사실 타임라인</h2>…</section>
<section data-section="limitations"><h2>확인할 수 없는 내용</h2>…</section>
<details data-section="major-negligence"><summary>12대 중과실 관련 확인 항목</summary>…</details>
<section data-section="emergency"><h2>긴급 번호</h2><p>119 · 구급/소방</p><p>112 · 경찰</p></section>
<details data-section="evidence"><summary>증거 상세</summary>…hashes and object tracking…</details>
<nav class="screen-only">…optional standalone-file save controls…</nav>
```

Render observation times relative to `incident_timestamp`, including `0.0초` for the incident and signed values elsewhere. Render each review status using these Korean labels:

```python
{
    "observed": "영상에서 관련 장면 관찰됨",
    "not_observed": "영상에서 관련 장면 관찰되지 않음",
    "not_determinable": "영상만으로 확인 불가",
}
```

Put object counts and detailed detector rows inside `증거 상세`; do not place them above the summary. Use responsive one-column CSS below 700px and retain printable keyframes.

- [ ] **Step 4: Run report tests**

Run:

```bash
pytest -q tests/test_reports.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add src/dashpi/reports.py tests/test_reports.py
git commit -m "feat: render evidence-first incident report"
```

---

### Task 3: Immediate native preview without a blank download slot

**Files:**
- Modify: `receiver-native/src/preview-model.ts`
- Test: `receiver-native/tests/preview-model.test.ts`
- Verify: `receiver-native/App.tsx`

**Interfaces:**
- Consumes: self-contained HTML with `section.screen-only[data-section="video"]`.
- Produces: existing `{kind: 'html', html, videos, playbackNotice}` preview model, with embedded video extracted for native playback and the empty source section removed.

- [ ] **Step 1: Add a failing preview-first test**

Update the HTML fixture in `receiver-native/tests/preview-model.test.ts` so the video is inside:

```html
<section class="video screen-only" data-section="video">
  <video controls preload="metadata" src="data:video/mp4;base64,..."></video>
</section>
<section data-section="summary"><h2>AI 핵심 요약</h2><p>사고 요약</p></section>
```

Extend the existing extraction test:

```typescript
assert.equal(model.videos.length, 1)
assert.equal(model.html.includes('data-section="video"'), false)
assert.match(model.html, /data-section="summary"/)
assert.equal(model.html.includes('Download HTML'), false)
assert.equal(model.html.includes('Save as PDF'), false)
```

- [ ] **Step 2: Run the focused native test and verify RED**

Run:

```bash
cd receiver-native && npm test -- --test-name-pattern='report keeps its pictures'
```

Expected: FAIL because the emptied video section remains in WebView HTML.

- [ ] **Step 3: Remove only the empty lifted-video section**

In `prepareHtml`, after `replaceVideoElements`, remove an empty `section` carrying both `screen-only` and `data-section="video"`. Do not remove arbitrary empty sections:

```typescript
const document = replaceVideoElements(stripSaveControls(html), extractVideo).replace(
  /<section\b(?=[^>]*\bscreen-only\b)(?=[^>]*\bdata-section\s*=\s*["']video["'])[^>]*>\s*<\/section>/gi,
  '',
)
```

Keep the current `VerifiedPreview` order in `App.tsx`: extracted native `ClipPlayer`, then HTML `WebView`. Keep `공유 또는 파일에 저장` outside and below `VerifiedPreview`; do not invoke it automatically.

- [ ] **Step 4: Run native tests and type/lint checks**

Run:

```bash
cd receiver-native
npm test
npx tsc --noEmit
npx expo lint
```

Expected: all tests and checks pass with no new warnings.

- [ ] **Step 5: Commit Task 3**

```bash
git add receiver-native/src/preview-model.ts receiver-native/tests/preview-model.test.ts
git commit -m "fix: show verified report before save actions"
```

---

### Task 4: End-to-end verification

**Files:**
- Modify only if a verification failure identifies a concrete defect in the files above.

**Interfaces:**
- Verifies the unchanged path: 45-second evidence → structured analysis → 10-second HTML payload → QR frames → verified native preview → optional share/save.

- [ ] **Step 1: Run the full Pi suite**

```bash
pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Run the receiver suite**

```bash
cd receiver-native
npm test
npx tsc --noEmit
npx expo lint
```

Expected: all checks pass.

- [ ] **Step 3: Run repository formatting checks**

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 4: Inspect one generated report**

Generate a report with the existing fake/simulated path and confirm, in order:

1. the 10-second clip is visible first;
2. three keyframes appear next;
3. summary, full-window timeline, limitations, 12-item review, emergency numbers, and evidence details follow;
4. no `tel:` URL exists;
5. the native receiver shows video and report before `공유 또는 파일에 저장`;
6. choosing share/save remains optional.

- [ ] **Step 5: Commit any verification-only fixture updates**

```bash
git add tests receiver-native/tests
git commit -m "test: verify evidence-first report flow"
```

Skip this commit when verification required no fixture changes.
