# Landing Header and Rails Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the language control beside the wordmark at every width and make the vertical rails a quiet background layer.

**Architecture:** Preserve the existing HTML and 12-column layout. Add one dedicated rail colour token, place page regions explicitly above the fixed rail layer, and remove the tablet breakpoint's overlapping grid columns.

**Tech Stack:** Vanilla HTML/CSS, Python `unittest`/pytest, browser responsive verification

## Global Constraints

- Keep the existing Hallmark Grid design, markup, copy, typography, spacing, and motion.
- Keep vertical rails visible at 320, 375, 414, 768, and desktop widths.
- Add no dependencies and delete no files.

---

### Task 1: Align the Header and Recede the Rails

**Files:**
- Modify: `landing/tokens.css:3-34`
- Modify: `landing/styles.css:6-27,66-93,181-193`
- Test: `tests/test_landing.py:72-91`

**Interfaces:**
- Consumes: existing `--color-paper`, `--color-rule`, `.rails`, `.topbar__grid`, and `.topbar__controls` CSS contracts
- Produces: `--color-rail`, explicit page-region stacking, and a non-overlapping header grid at the tablet breakpoint

- [ ] **Step 1: Write the failing CSS contract test**

Extend `test_grid_theme_contract` with these assertions:

```python
self.assertIn("--color-rail: oklch(95.5% 0.003 255);", tokens)
self.assertIn("var(--color-rail) 0", styles)
self.assertIn("body > header, body > main, body > footer { position: relative; z-index: 1; }", styles)
self.assertIn(".topbar__controls { grid-column: 6 / 13; grid-row: 1; }", styles)
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
/Users/justin/Documents/ChatGPT/DashPi/.venv/bin/python -m pytest tests/test_landing.py::LandingPageTests::test_grid_theme_contract -q
```

Expected: FAIL because `--color-rail` and the corrected stacking/header rules do not exist.

- [ ] **Step 3: Implement the minimal CSS change**

Add the token to `landing/tokens.css`:

```css
--color-rail: oklch(95.5% 0.003 255);
```

In `landing/styles.css`, place the page regions above `.rails`, use the new token in the rail gradient, and correct the breakpoint rule:

```css
body > header, body > main, body > footer { position: relative; z-index: 1; }

.rails {
  position: fixed;
  inset: 0;
  z-index: 0;
  max-width: var(--shell-max);
  margin-inline: auto;
  padding-inline: var(--gutter);
  background-clip: content-box;
  background-image: repeating-linear-gradient(to right,
    var(--color-rail) 0,
    var(--color-rail) var(--rule-hairline),
    transparent var(--rule-hairline),
    transparent calc(100% / 12));
  pointer-events: none;
}

@media (max-width: 60rem) {
  .topbar__controls { grid-column: 6 / 13; grid-row: 1; }
}
```

- [ ] **Step 4: Run focused and full automated verification**

Run:

```bash
/Users/justin/Documents/ChatGPT/DashPi/.venv/bin/python -m pytest tests/test_landing.py -q
/Users/justin/Documents/ChatGPT/DashPi/.venv/bin/python -m pytest -q
git diff --check
```

Expected: 11 landing tests pass, 307 full Python tests pass, and `git diff --check` prints nothing.

- [ ] **Step 5: Verify responsive rendering**

At `http://127.0.0.1:4174/`, verify widths 320, 375, 414, and 768 px:

- `document.documentElement.scrollWidth <= document.documentElement.clientWidth`
- `.wordmark` and `.language-toggle` have equal vertical centre points within 1 px.
- `.rails` remains visible and its computed background uses `--color-rail`.
- Korean and English toggles preserve the single-row header.
- Browser console contains no errors.

- [ ] **Step 6: Run Hallmark handoff checks and commit**

Load `references/slop-test.md` and `references/contract.md`, confirm the targeted change introduces no new failures, then commit:

```bash
git add landing/tokens.css landing/styles.css tests/test_landing.py
git commit -m "fix: align landing header and soften grid rails"
```
