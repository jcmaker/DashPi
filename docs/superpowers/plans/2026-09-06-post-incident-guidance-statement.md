# Post-incident Guidance Statement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the landing page's AI-failure statement with a concise explanation of DashPi's post-crash guidance and handoff value.

**Architecture:** Reuse the existing statement-band markup and i18n dictionary. Change only its headline, supporting copy, decorative word, styling needed for the longer paragraph, and the focused landing regression test.

**Tech Stack:** Static HTML, CSS, inline JavaScript translation dictionary, Python `unittest` via pytest.

## Global Constraints

- Do not imply that DashPi determines fault, legal responsibility, or a definitive interpretation of the crash.
- Do not change the surrounding flow, evidence, transfer, verification, or footer sections.
- Reuse the existing statement-band markup, translation mechanism, and typography.

---

### Task 1: Replace the statement-band message

**Files:**
- Modify: `landing/index.html`
- Modify: `landing/styles.css`
- Test: `tests/test_landing.py`

**Interfaces:**
- Consumes: existing `data-i18n` translation hooks and `.plate` layout.
- Produces: `plate.title` and `plate.description` copy in Korean and English, plus a decorative `NEXT` word.

- [ ] **Step 1: Write the failing regression test**

```python
def test_statement_explains_post_incident_guidance(self) -> None:
    page = self.page()
    self.assertIn("사고 직후에는, 무엇을 해야 할지 판단하기 어렵습니다.", page)
    self.assertIn("경찰·보험사 등 제3자에게 빠뜨리지 않고 상황을 전달할 수 있습니다.", page)
    self.assertIn('class="numeral" aria-hidden="true">NEXT</span>', page)
    self.assertIn('"plate.description": "DashPi organizes the recorded situation and next steps.', page)
    self.assertNotIn("AI가 실패해도, 증거는 남습니다.", page)
    self.assertNotIn('class="numeral" aria-hidden="true">45</span>', page)
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `.venv/bin/python -m pytest tests/test_landing.py -q`

Expected: FAIL because the old statement band is still present.

- [ ] **Step 3: Implement the minimal content change**

Use this Korean copy:

```text
사고 직후에는, 무엇을 해야 할지 판단하기 어렵습니다.
DashPi는 사고 전후 기록을 바탕으로 상황과 필요한 조치를 정리합니다. 운전자는 해야 할 일을 확인하고, 경찰·보험사 등 제3자에게 빠뜨리지 않고 상황을 전달할 수 있습니다.
```

Use this English copy:

```text
Right after a crash, it can be hard to know what to do.
DashPi organizes the recorded situation and next steps. Drivers can see what they need to do and hand over the relevant facts to police, insurers, and other responders without omissions.
```

Replace decorative `45` with `NEXT`, and update the existing `.plate .label` rule only as needed to keep the longer copy readable.

- [ ] **Step 4: Run focused and full verification**

Run:

```bash
.venv/bin/python -m pytest tests/test_landing.py -q
.venv/bin/python -m pytest -q
npm test --prefix web
npm run build --prefix web
git diff --check
```

Expected: all tests and builds pass; the existing intentional web skip remains acceptable.

- [ ] **Step 5: Commit and push**

```bash
git add landing/index.html landing/styles.css tests/test_landing.py
git commit -m "feat: explain post-incident guidance on landing page"
git push origin main
```
