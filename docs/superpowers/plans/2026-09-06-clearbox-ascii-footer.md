# Clearbox ASCII Footer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dark origin panel to the landing footer with Clearbox history copy and a slowly rotating decorative ASCII cube.

**Architecture:** Extend the existing footer in place. A single semantic copy block carries the meaning; one decorative `<pre>` provides a no-JavaScript fallback, and the existing landing script swaps a fixed set of ASCII frames with `requestAnimationFrame` unless reduced motion is enabled.

**Tech Stack:** Static HTML, CSS tokens, vanilla JavaScript, Python `unittest` via pytest.

## Global Constraints

- Do not add canvas, WebGL, dependencies, controls, or keyboard interaction.
- The ASCII cube must be `aria-hidden="true"`; adjacent translated copy carries the meaning.
- `prefers-reduced-motion: reduce` must leave a stable first frame.
- Preserve the existing Grid theme, Archivo/Noto Sans KR typography, spacing tokens, red accent, and lower document-link strip.
- Do not change unrelated landing sections or delete files.

---

### Task 1: Build the Clearbox origin footer

**Files:**
- Modify: `landing/index.html`
- Modify: `landing/tokens.css`
- Modify: `landing/styles.css`
- Modify: `landing/script.js`
- Test: `tests/test_landing.py`

**Interfaces:**
- Consumes: existing `.footer`, `.shell`, translation dictionary, `requestAnimationFrame`, and `prefers-reduced-motion` support.
- Produces: `[data-clearbox-cube]`, `footer.origin.eyebrow`, `footer.origin.title`, `footer.origin.description`, and `--font-mono`.

- [ ] **Step 1: Write the failing footer regression test**

Add this test to `LandingPageTests`:

```python
def test_footer_honors_clearbox_with_a_reduced_motion_ascii_cube(self) -> None:
    page = self.page()
    styles = (LANDING / "styles.css").read_text(encoding="utf-8")
    script = (LANDING / "script.js").read_text(encoding="utf-8")
    translations = self.translations()

    self.assertIn('data-i18n="footer.origin.title"', page)
    self.assertIn('data-clearbox-cube aria-hidden="true"', page)
    self.assertEqual(translations["ko"]["footer.origin.title"], "DashPi는 Clearbox에서 시작되었습니다.")
    self.assertEqual(translations["en"]["footer.origin.title"], "DashPi began as Clearbox.")
    self.assertIn("--font-mono:", (LANDING / "tokens.css").read_text(encoding="utf-8"))
    self.assertIn(".footer__origin", styles)
    self.assertIn("const CLEARBOX_FRAMES", script)
    self.assertIn('matchMedia("(prefers-reduced-motion: reduce)")', script)
    self.assertIn("requestAnimationFrame(animateClearboxCube)", script)
    self.assertNotIn("setInterval", script)
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_landing.py::LandingPageTests::test_footer_honors_clearbox_with_a_reduced_motion_ascii_cube -q
```

Expected: FAIL because the origin panel and cube do not exist.

- [ ] **Step 3: Add semantic footer markup and translations**

Add a `.footer__origin` section above the existing `.footer__grid`. It contains:

```html
<div class="footer__origin" aria-labelledby="footer-origin-title">
  <div class="shell footer__origin-grid">
    <div class="footer__origin-copy">
      <p class="eyebrow" data-i18n="footer.origin.eyebrow">ORIGIN / CLEARBOX</p>
      <h2 id="footer-origin-title" data-i18n="footer.origin.title">DashPi는 Clearbox에서 시작되었습니다.</h2>
      <p data-i18n="footer.origin.description">사고 직후의 혼란을, 더 명확한 기록과 전달로 바꾸기 위한 첫 이름이었습니다.</p>
    </div>
    <pre class="footer__cube" data-clearbox-cube aria-hidden="true">        +----------+
       /          /|
      +----------+ |
      |          | |
      |          | +
      |          |/
      +----------+</pre>
  </div>
</div>
```

Add equivalent Korean and English values for all three `footer.origin.*` keys. Keep the lower footer links unchanged.

- [ ] **Step 4: Add the token and responsive footer styling**

Add a system monospace token to `landing/tokens.css`:

```css
--font-mono: ui-monospace, "SFMono-Regular", Consolas, "Liberation Mono", monospace;
```

Use these rules as the layout basis, integrating them with the current footer declarations rather than duplicating selectors:

```css
.footer { border-top: var(--rule-hairline) solid var(--color-ink); }
.footer__origin { display: grid; align-items: center; min-height: clamp(480px, 55vh, 640px); overflow: clip; background: var(--color-ink); color: var(--color-paper); }
.footer__origin-grid { align-items: center; padding-block: var(--space-8); }
.footer__origin-copy { grid-column: 1 / 7; }
.footer__origin-copy .eyebrow { margin-block-end: var(--space-4); color: var(--color-paper-3); }
.footer__origin-copy h2 { font-size: clamp(36px, 5vw, 64px); }
.footer__origin-copy > p:last-child { max-width: 46ch; margin-block-start: var(--space-5); color: var(--color-paper-2); font-size: 18px; line-height: 1.7; word-break: keep-all; }
.footer__cube { grid-column: 7 / 13; justify-self: end; width: 24ch; min-height: 7.35em; overflow: hidden; color: var(--color-accent); font-family: var(--font-mono); font-size: clamp(11px, 1.45vw, 18px); line-height: 1.05; white-space: pre; user-select: none; }
.footer__grid { align-items: center; row-gap: var(--space-2); padding-block: var(--space-4); }

@media (max-width: 40rem) {
  .footer__origin-copy, .footer__cube { grid-column: 1 / 13; }
  .footer__cube { justify-self: center; margin-block-start: var(--space-6); }
}
```

- [ ] **Step 5: Add the minimal ASCII frame loop**

In `landing/script.js`, define these five fixed-width, seven-line cube frames and cycle through the index sequence `[0, 1, 2, 3, 4, 3, 2, 1]` every 420 ms. Use one `requestAnimationFrame` loop:

```javascript
const CLEARBOX_FRAMES = [
  String.raw`        +----------+
       /          /|
      +----------+ |
      |          | |
      |          | +
      |          |/
      +----------+`,
  String.raw`          +-------+
        //       /|
       ++-------+ |
       ||       | |
       ||       | +
       ||       |/
       ++-------+`,
  String.raw`             +--+
            /  /|
           +--+ |
           |  | |
           |  | +
           |  |/
           +--+`,
  String.raw`       +-------+
       |\       \\
       | +-------++
       | |       ||
       + |       ||
        \|       ||
         +-------++`,
  String.raw`      +----------+
      |\          \\
      | +----------+
      | |          |
      + |          |
       \|          |
        +----------+`,
];
const CLEARBOX_ORDER = [0, 1, 2, 3, 4, 3, 2, 1];
const cube = document.querySelector("[data-clearbox-cube]");
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
let cubeFrame = 0;
let previousFrameTime = 0;

function animateClearboxCube(time) {
  if (time - previousFrameTime >= 420) {
    cubeFrame = (cubeFrame + 1) % CLEARBOX_ORDER.length;
    cube.textContent = CLEARBOX_FRAMES[CLEARBOX_ORDER[cubeFrame]];
    previousFrameTime = time;
  }
  requestAnimationFrame(animateClearboxCube);
}

if (cube && !reducedMotion.matches) requestAnimationFrame(animateClearboxCube);
```

The first HTML frame and `CLEARBOX_FRAMES[0]` must match visually.

- [ ] **Step 6: Verify GREEN and inspect the browser**

Run:

```bash
.venv/bin/python -m pytest tests/test_landing.py -q
```

Then verify both languages, slow frame motion, stable reduced-motion fallback, and zero horizontal overflow at 320, 375, 414, 768, and desktop widths.

- [ ] **Step 7: Run the full project checks**

Run:

```bash
.venv/bin/python -m pytest -q
npm test --prefix web
npm run build --prefix web
git diff --check
```

Expected: all tests and builds pass; the existing intentional web skip remains acceptable.

- [ ] **Step 8: Commit and push to main**

```bash
git add landing/index.html landing/tokens.css landing/styles.css landing/script.js tests/test_landing.py
git commit -m "feat: honor Clearbox in animated landing footer"
git push origin main
```
