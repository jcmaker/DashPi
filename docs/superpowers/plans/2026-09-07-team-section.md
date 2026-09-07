# School and Team Section Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an accessible, bilingual school and team section between verification and the GitHub call-to-action.

**Architecture:** Extend the existing static landing markup, CSS grid, and inline i18n dictionary. Keep all six contributors equal; render roles only where known and add no JavaScript or dependencies.

**Tech Stack:** Static HTML, CSS, inline JSON translations, Python `unittest` via pytest.

## Global Constraints

- Use `경기과학기술대학교 · 디자인공학과 · 캡스톤디자인` and `이 프로젝트를 만든 사람들` in Korean.
- Show 조준형 — Software, 채현수 — Hardware · CAD, 우지혁 — CAD, plus 최재혁, 최준명, and 신태영 without placeholder roles.
- Place the section after Verification and before the GitHub source call-to-action.
- Reuse the existing grid, design tokens, and language-toggle mechanism.
- Add no portraits, biographies, social links, JavaScript behavior, or dependencies.

---

### Task 1: Add the school and team section

**Files:**
- Modify: `landing/index.html:232`
- Modify: `landing/styles.css:167`
- Test: `tests/test_landing.py`

**Interfaces:**
- Consumes: `.shell`, `.section-heading`, `.eyebrow`, design tokens, and `data-i18n` translation hooks.
- Produces: `#team`, `.team__grid`, `.team__member`, and `team.*` translation keys.

- [ ] **Step 1: Write the failing regression test**

```python
def test_school_and_team_section_is_complete_and_precedes_source(self) -> None:
    page = self.page()
    parser = self.parser()
    translations = self.translations()

    self.assertIn("team", parser.ids)
    self.assertLess(page.index('id="verification"'), page.index('id="team"'))
    self.assertLess(page.index('id="team"'), page.index('id="source"'))
    self.assertEqual(translations["ko"]["team.school"], "경기과학기술대학교 · 디자인공학과 · 캡스톤디자인")
    self.assertEqual(translations["en"]["team.school"], "Gyeonggi University of Science and Technology · Department of Design Engineering · Capstone Design")
    self.assertEqual(translations["en"]["team.title"], "Meet the team")
    for name in ("조준형", "채현수", "우지혁", "최재혁", "최준명", "신태영"):
        self.assertIn(name, page)
    self.assertNotIn("확인 필요", page)
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `.venv/bin/python -m pytest tests/test_landing.py::LandingPageTests::test_school_and_team_section_is_complete_and_precedes_source -q`

Expected: FAIL because `#team` and the `team.*` translations do not exist.

- [ ] **Step 3: Add the minimal semantic markup and translations**

Insert a `<section class="team" id="team" aria-labelledby="team-title">` between the existing Verification and Source sections. Inside the existing `.shell`, add the school eyebrow, heading, and an unordered list of six `.team__member` entries. Give only the first three entries role paragraphs. Add matching Korean and English `team.school`, `team.title`, `team.member.*.name`, and known `team.member.*.role` values to the existing JSON dictionaries; keep names unchanged in English and use `Gyeonggi University of Science and Technology · Department of Design Engineering · Capstone Design` for the English school line.

- [ ] **Step 4: Add the responsive grid styling**

```css
.team { padding-block: var(--space-band); border-top: var(--rule-section) solid var(--color-ink); }
.team__school { grid-column: 1 / 13; margin-block-end: var(--space-3); }
.team .section-heading { margin-block-end: var(--space-6); }
.team__grid { grid-column: 1 / 13; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); list-style: none; border-block: var(--rule-hairline) solid var(--color-ink); }
.team__member { min-height: 144px; padding: var(--space-5); border-inline-start: var(--rule-hairline) solid var(--color-rule); }
.team__member:nth-child(n + 4) { border-top: var(--rule-hairline) solid var(--color-rule); }
.team__member:nth-child(3n) { border-inline-end: var(--rule-hairline) solid var(--color-rule); }
.team__member h3 { font-size: clamp(20px, 2.2vw, 28px); }
.team__role { margin-block-start: var(--space-3); color: var(--color-muted); font-size: 12px; font-weight: 600; letter-spacing: var(--tracking-label); text-transform: uppercase; }

@media (max-width: 40rem) {
  .team__grid { grid-template-columns: minmax(0, 1fr); }
  .team__member { min-height: 112px; border-inline-end: var(--rule-hairline) solid var(--color-rule); }
  .team__member + .team__member { border-top: var(--rule-hairline) solid var(--color-rule); }
}
```

- [ ] **Step 5: Run focused and full verification**

Run:

```bash
.venv/bin/python -m pytest tests/test_landing.py::LandingPageTests::test_school_and_team_section_is_complete_and_precedes_source -q
.venv/bin/python -m pytest tests/test_landing.py -q
.venv/bin/python -m pytest -q
npm test --prefix web
npm run build --prefix web
git diff --check
```

Expected: all checks pass; the existing intentional web test skip remains acceptable.

- [ ] **Step 6: Commit the implementation**

```bash
git add landing/index.html landing/styles.css tests/test_landing.py docs/superpowers/plans/2026-09-07-team-section.md
git commit -m "feat: add school and team section"
```
