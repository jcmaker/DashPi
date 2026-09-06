# Clearbox Cube Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cycle the solid Clearbox cube from white to red, enrich its ASCII shading, and shorten one revolution from roughly 42 seconds to 30 seconds.

**Architecture:** Keep the existing dependency-free ray-cast renderer and `<pre>` output. CSS owns the foreground colour cycle; the renderer owns glyph selection through a longer shade ramp plus deterministic screen-space variation; the existing animation loop owns rotation timing.

**Tech Stack:** HTML/CSS, browser JavaScript, Python `unittest`, Node VM harness

## Global Constraints

- Reuse the existing paper and accent colour tokens; add no colour tokens or dependencies.
- Keep the current low render cap, footer layout, solid silhouette, and no-control interaction model.
- Disable both colour and rotation animation under `prefers-reduced-motion: reduce`.
- Modify only `landing/styles.css`, `landing/script.js`, and `tests/test_landing.py`.

---

### Task 1: Polish the Clearbox cube

**Files:**
- Modify: `tests/test_landing.py`
- Modify: `landing/styles.css`
- Modify: `landing/script.js`

**Interfaces:**
- Consumes: `.footer__cube`, `renderClearboxCube(angle: number): string`, `animateClearboxCube(time: number): void`, `--color-paper`, and `--color-accent`.
- Produces: `clearbox-color` CSS animation, a richer `CUBE_SHADES` ramp, and a 30,000 ms rotation period.

- [x] **Step 1: Write the failing tests**

Add separate assertions to `tests/test_landing.py` that require the CSS colour cycle, at least six distinct non-space glyphs in a rendered frame, and a half-turn angle after `animateClearboxCube(15000)`:

```python
def test_footer_cube_cycles_between_white_and_red(self) -> None:
    styles = (LANDING / "styles.css").read_text(encoding="utf-8")
    self.assertRegex(styles, r"@keyframes clearbox-color\s*\{")
    self.assertRegex(styles, r"0%,\s*100%\s*\{\s*color:\s*var\(--color-paper\)")
    self.assertRegex(styles, r"50%\s*\{\s*color:\s*var\(--color-accent\)")
    self.assertRegex(styles, r"\.footer__cube\s*\{[^}]*animation:\s*clearbox-color")
```

Wrap the renderer in the existing Node VM harness, call the animation once, and expose the angle it received:

```javascript
const renderedAngles = [];
const render = renderClearboxCube;
renderClearboxCube = (angle) => {
  renderedAngles.push(angle);
  return render(angle);
};
const scheduledBeforeManualAnimation = [...scheduled];
animateClearboxCube(15000);
globalThis.result = {
  first: render(0),
  rotated: render(0.7),
  scheduledBeforeManualAnimation,
  animatedAngle: renderedAngles.at(-1),
};
```

Then assert:

```python
self.assertGreaterEqual(len(set(visible)), 6)
self.assertAlmostEqual(rendered["animatedAngle"], 3.141592653589793)
```

- [x] **Step 2: Run the focused test to verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_landing.py -q
```

Expected: FAIL because `clearbox-color` does not exist, the current frame uses fewer than six visible glyphs, and 15,000 ms is not half of a revolution.

- [x] **Step 3: Add the CSS colour cycle**

Add one keyframe and attach it to the existing cube rule:

```css
@keyframes clearbox-color {
  0%, 100% { color: var(--color-paper); }
  50% { color: var(--color-accent); }
}

.footer__cube {
  color: var(--color-paper);
  animation: clearbox-color 8s ease-in-out infinite;
}
```

The existing global reduced-motion rule already sets `animation: none !important`.

- [x] **Step 4: Enrich glyph shading and speed up rotation**

Replace the short shade ramp and use the existing row and column values to vary adjacent shade selection without new DOM nodes:

```javascript
const CUBE_SHADES = " .,:;irsXA253hMHGS#9B&@";
const CUBE_ROTATION_PERIOD = 30000;

const variation = ((column * 17 + row * 11) % 9 - 4) * 0.012;
const lightLevel = Math.max(0, Math.min(1, 0.18 + 0.72 * luminance
  + 0.1 * (1 - row / CUBE_ROWS) + variation));
const shade = Math.floor(lightLevel * (CUBE_SHADES.length - 1));
```

Drive the angle by the explicit period:

```javascript
cube.textContent = renderClearboxCube(time * Math.PI * 2 / CUBE_ROTATION_PERIOD);
```

- [x] **Step 5: Verify GREEN and the full project**

Run:

```bash
.venv/bin/python -m pytest tests/test_landing.py -q
.venv/bin/python -m pytest -q
npm test --prefix web -- --run
npm run build --prefix web
node --check landing/script.js
git diff --check
```

Expected: all tests and checks pass.

- [x] **Step 6: Inspect the local preview and commit**

Check `http://127.0.0.1:4174/` at desktop and mobile widths, confirming the colour cycle, richer glyph variation, faster rotation, and no horizontal overflow. Then commit:

```bash
git add landing/styles.css landing/script.js tests/test_landing.py docs/superpowers/plans/2026-09-06-clearbox-cube-polish.md
git commit -m "feat: polish Clearbox cube animation"
```
