# Hero Recording Viewfinder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hero incident motif with a proportional, text-free recording viewfinder.

**Architecture:** Reuse `.hero__composition` as the viewfinder canvas and draw its four open corners with layered CSS backgrounds. Two decorative children provide the red recording indicator and central focus window; percentage geometry and the existing `5 / 3` aspect ratio keep one composition across breakpoints.

**Tech Stack:** Vanilla HTML/CSS, Python pytest, Chromium responsive verification

## Global Constraints

- Modify only `landing/index.html`, `landing/styles.css`, and `tests/test_landing.py`.
- Use the existing paper, ink, rule, and accent tokens.
- Add no dependency, JavaScript, text badge, or animation.
- Do not change landing copy, the statement section, the footer, or any other section.
- Add no breakpoint-specific viewfinder geometry.

---

### Task 1: Replace the Hero Motif With a Recording Viewfinder

**Files:**
- Modify: `landing/index.html:45-48`
- Modify: `landing/index.html:250,331`
- Modify: `landing/styles.css:101-112`
- Test: `tests/test_landing.py:70-83`

**Interfaces:**
- Consumes: `.hero__composition`, `--color-ink`, `--color-accent`, `--rule-section`, and the `hero.artLabel` translation key
- Produces: `.viewfinder`, `.recording-indicator`, and `.focus-window`

- [ ] **Step 1: Write the failing contract test**

Replace the two current hero-art tests with:

```python
def test_hero_art_has_a_korean_no_javascript_label(self) -> None:
    self.assertIn(
        'role="img" aria-label="영상 녹화와 사고 시점 포착을 표현한 카메라 뷰파인더"',
        self.page(),
    )

def test_hero_art_uses_a_responsive_recording_viewfinder(self) -> None:
    page = self.page()
    styles = (LANDING / "styles.css").read_text(encoding="utf-8")
    for legacy in ("finder", "incident-window", "clip-strip"):
        self.assertNotIn(f'class="{legacy}"', page)
        self.assertNotIn(f".{legacy}", styles)
    self.assertIn('class="hero__composition viewfinder"', page)
    self.assertIn('class="recording-indicator"', page)
    self.assertIn('class="focus-window"', page)
    self.assertIn(".viewfinder", styles)
    self.assertIn(".recording-indicator", styles)
    self.assertIn(".focus-window", styles)
    self.assertIn(
        '"hero.artLabel": "Camera viewfinder representing video recording and incident capture"',
        page,
    )
```

- [ ] **Step 2: Run the focused test to verify RED**

Run:

```bash
/Users/justin/Documents/ChatGPT/DashPi/.venv/bin/python -m pytest tests/test_landing.py::LandingPageTests::test_hero_art_has_a_korean_no_javascript_label tests/test_landing.py::LandingPageTests::test_hero_art_uses_a_responsive_recording_viewfinder -q
```

Expected: FAIL because the old label and incident motif still exist.

- [ ] **Step 3: Implement the minimal viewfinder markup**

Replace the hero composition with:

```html
<div class="hero__composition viewfinder" role="img" aria-label="영상 녹화와 사고 시점 포착을 표현한 카메라 뷰파인더" data-i18n-attr="aria-label:hero.artLabel">
  <span class="recording-indicator" aria-hidden="true"></span>
  <span class="focus-window" aria-hidden="true"></span>
</div>
```

Set the Korean translation to `영상 녹화와 사고 시점 포착을 표현한 카메라 뷰파인더` and the English translation to `Camera viewfinder representing video recording and incident capture`.

- [ ] **Step 4: Implement the proportional CSS artwork**

Delete the `.finder`, `.incident-window`, and `.clip-strip` rules. Keep the existing `.hero__composition` layout rule and add:

```css
.viewfinder {
  background:
    linear-gradient(var(--color-ink) 0 0) left top / 24% var(--rule-section) no-repeat,
    linear-gradient(var(--color-ink) 0 0) left top / var(--rule-section) 36% no-repeat,
    linear-gradient(var(--color-ink) 0 0) right top / 24% var(--rule-section) no-repeat,
    linear-gradient(var(--color-ink) 0 0) right top / var(--rule-section) 36% no-repeat,
    linear-gradient(var(--color-ink) 0 0) left bottom / 24% var(--rule-section) no-repeat,
    linear-gradient(var(--color-ink) 0 0) left bottom / var(--rule-section) 36% no-repeat,
    linear-gradient(var(--color-ink) 0 0) right bottom / 24% var(--rule-section) no-repeat,
    linear-gradient(var(--color-ink) 0 0) right bottom / var(--rule-section) 36% no-repeat;
}
.recording-indicator { position: absolute; inset-block-start: 12%; inset-inline-start: 10%; width: 7%; aspect-ratio: 1; border-radius: 50%; background: var(--color-accent); }
.focus-window { position: absolute; inset-block-start: 32.5%; inset-inline-start: 36%; width: 28%; aspect-ratio: 4 / 3; border: var(--rule-hairline) solid var(--color-ink); }
.focus-window::after { content: ""; position: absolute; inset-block-start: 39%; inset-inline-start: 39%; width: 22%; aspect-ratio: 1; background: var(--color-accent); }
```

- [ ] **Step 5: Verify GREEN and the full automated suite**

Run:

```bash
/Users/justin/Documents/ChatGPT/DashPi/.venv/bin/python -m pytest tests/test_landing.py -q
/Users/justin/Documents/ChatGPT/DashPi/.venv/bin/python -m pytest -q
npm test --prefix web
npm run build --prefix web
git diff --check
```

Expected: all commands exit `0`.

- [ ] **Step 6: Verify real responsive rendering**

At 320, 375, 414, 768, 1280, and 1920 CSS pixels, use Chromium to confirm:

- `document.documentElement.scrollWidth === document.documentElement.clientWidth`
- `.viewfinder`, `.recording-indicator`, and `.focus-window` have identical normalised bounding boxes at every width
- no browser exception or error overlay exists
- Korean and English modes expose the specified accessible labels
- the complete hero and viewfinder focal point fit at 1280 × 800

- [ ] **Step 7: Commit and push `main`**

```bash
git add landing/index.html landing/styles.css tests/test_landing.py
git commit -m "feat: replace hero motif with recording viewfinder"
git push origin main
```
