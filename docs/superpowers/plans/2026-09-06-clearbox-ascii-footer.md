# Clearbox Solid ASCII Footer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the full landing footer into one dark closing panel with Clearbox history copy and a slowly rotating solid, character-shaded cube.

**Architecture:** Keep the current semantic footer and decorative `<pre>` slot. Replace the outline frame array with a small ray-cast cube renderer that fills visible faces from a glyph shade ramp, then update the `<pre>` at a restrained frame rate through `requestAnimationFrame` unless reduced motion is enabled. The origin panel and lower document-link strip share one dark footer surface.

**Tech Stack:** Static HTML, CSS tokens, vanilla JavaScript, Python `unittest` via pytest.

## Global Constraints

- Do not add canvas, WebGL, dependencies, controls, or keyboard interaction.
- The cube must be solid rather than outline-only and remain `aria-hidden="true"`; adjacent translated copy carries the meaning.
- `prefers-reduced-motion: reduce` must leave a stable solid frame.
- Preserve the existing Grid theme, Archivo/Noto Sans KR typography, spacing tokens, and red accent.
- The dark footer surface must include `DASHPI · 2026`, README, PRD, TRD, and the third-party notice link.
- Do not change unrelated landing sections or delete files.

---

### Task 1: Replace the outline cube with a solid footer renderer

**Files:**
- Modify: `landing/index.html`
- Modify: `landing/styles.css`
- Modify: `landing/script.js`
- Test: `tests/test_landing.py`

**Interfaces:**
- Consumes: existing `.footer`, `.footer__origin`, `.footer__grid`, `[data-clearbox-cube]`, design tokens, `requestAnimationFrame`, and `prefers-reduced-motion`.
- Produces: `renderClearboxCube(angle: number): string`, a solid fallback frame, and one continuous dark footer surface.

- [ ] **Step 1: Write the failing regression test**

Update the footer regression in `LandingPageTests` to require the solid renderer and dark lower strip:

```python
def test_footer_uses_a_solid_cube_and_one_dark_surface(self) -> None:
    page = self.page()
    styles = (LANDING / "styles.css").read_text(encoding="utf-8")
    script = (LANDING / "script.js").read_text(encoding="utf-8")

    self.assertIn('data-clearbox-cube aria-hidden="true"', page)
    self.assertIn("function renderClearboxCube", script)
    self.assertIn("const CUBE_SHADES", script)
    self.assertNotIn("const CLEARBOX_FRAMES", script)
    self.assertIn(".footer__grid .label", styles)
```

Add a Node VM harness inside the test that runs `renderClearboxCube` with controlled DOM globals. Assert that a frame has 20 rows, more than 120 non-space glyphs, at least three shade glyphs, and differs at two angles. This catches regressions back to an outline or static frame sequence.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_landing.py::LandingPageTests::test_footer_uses_a_solid_cube_and_one_dark_surface -q
```

Expected: FAIL because the current implementation still exposes `CLEARBOX_FRAMES` and has no `renderClearboxCube`.

- [ ] **Step 3: Replace the static fallback**

Keep the current footer structure and translations. Replace the seven-line outline inside `[data-clearbox-cube]` with the filled 40-column by 20-row result of `renderClearboxCube(0)` so no-JavaScript visitors see the intended solid form.

- [ ] **Step 4: Make the whole footer one dark responsive surface**

Move the dark surface and light foreground to `.footer`, keep `.footer__origin` transparent, and give `.footer__grid` a subdued top rule. Override footer labels with an existing light paper token. Size the cube to `40ch` with `font-size: clamp(10px, 1.25vw, 16px)` and keep the existing single-column mobile layout.

```css
.footer { border-top: var(--rule-hairline) solid var(--color-ink); background: var(--color-ink); color: var(--color-paper); }
.footer__origin { display: grid; align-items: center; min-height: clamp(520px, 62vh, 720px); overflow: clip; }
.footer__cube { width: 40ch; min-height: 20em; font-size: clamp(10px, 1.25vw, 16px); line-height: 1; }
.footer__grid { border-top: var(--rule-hairline) solid var(--color-muted); }
.footer__grid .label { color: var(--color-paper-2); }
```

- [ ] **Step 5: Add the minimal solid cube renderer**

Replace `CLEARBOX_FRAMES` and `CLEARBOX_ORDER` with fixed grid and shade constants plus `renderClearboxCube(angle)`. For each character cell, transform a camera ray into cube-local space, intersect the `[-1, 1]` cube with the slab method, rotate the nearest face normal back to world space, and map its light value into `CUBE_SHADES`.

```javascript
const CUBE_COLUMNS = 40;
const CUBE_ROWS = 20;
const CUBE_SHADES = " .:-=+*#%@";

function renderClearboxCube(angle) {
  // Returns exactly CUBE_ROWS lines of shaded character cells.
}
```

Render at most once every 120 ms. Use `time * 0.00015` for a slow time-based Y rotation and a fixed X tilt. When reduced motion is active, render only `renderClearboxCube(0)` and schedule no cube animation frame.

- [ ] **Step 6: Verify GREEN and inspect the browser**

Run:

```bash
.venv/bin/python -m pytest tests/test_landing.py -q
```

Then verify both languages, solid face shading, slow frame motion, stable reduced-motion fallback, one continuous dark footer, and zero horizontal overflow at 320, 375, 414, 768, and desktop widths.

- [ ] **Step 7: Run the full project checks**

Run:

```bash
.venv/bin/python -m pytest -q
npm test --prefix web
npm run build --prefix web
node --check landing/script.js
git diff --check
```

Expected: all tests and builds pass; the existing intentional web skip remains acceptable.

- [ ] **Step 8: Commit and push to main**

```bash
git add landing/index.html landing/styles.css landing/script.js tests/test_landing.py docs/superpowers/specs/2026-09-06-clearbox-ascii-footer-design.md docs/superpowers/plans/2026-09-06-clearbox-ascii-footer.md
git commit -m "feat: render solid Clearbox cube in landing footer"
git push origin main
```
