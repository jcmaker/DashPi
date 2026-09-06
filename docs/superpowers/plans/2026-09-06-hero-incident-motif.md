# Hero Incident Motif Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hero SHA badge and ornament with a proportional, text-free incident motif.

**Architecture:** Reuse the existing hero composition container and token palette. Three CSS shapes—optical finder, incident window, and three-cell clip strip—use percentage positioning and fixed aspect ratios so one geometry works at every breakpoint.

**Tech Stack:** Vanilla HTML/CSS, Python pytest, browser responsive verification

## Global Constraints

- Change only the hero motif and its accessible label.
- Do not change landing copy, the statement section, or footer content.
- Add no dependency and no breakpoint-specific motif geometry.

---

### Task 1: Replace the Hero Motif

**Files:**
- Modify: `landing/index.html`
- Modify: `landing/styles.css`
- Test: `tests/test_landing.py`

**Interfaces:**
- Consumes: `.hero__composition`, `--color-paper`, `--color-ink`, and `--color-accent`
- Produces: `.finder`, `.incident-window`, and `.clip-strip`

- [ ] **Step 1: Write the failing test**

```python
def test_hero_art_uses_a_responsive_incident_motif(self) -> None:
    page = self.page()
    styles = (LANDING / "styles.css").read_text(encoding="utf-8")
    self.assertNotIn("SHA<br>256", page)
    self.assertNotIn("verification-square", page + styles)
    self.assertIn('class="incident-window"', page)
    self.assertIn('class="clip-strip"', page)
    self.assertIn(".incident-window", styles)
    self.assertIn(".clip-strip", styles)
```

- [ ] **Step 2: Verify RED**

Run:

```bash
/Users/justin/Documents/ChatGPT/DashPi/.venv/bin/python -m pytest tests/test_landing.py::LandingPageTests::test_hero_art_uses_a_responsive_incident_motif -q
```

Expected: FAIL because the SHA badge and legacy selector still exist.

- [ ] **Step 3: Implement the minimal motif**

Replace the legacy hero-art children with:

```html
<div class="finder" aria-hidden="true"></div>
<div class="incident-window" aria-hidden="true"></div>
<div class="clip-strip" aria-hidden="true"><span></span><span></span><span></span></div>
```

Update `hero.artLabel` in both languages to describe incident preservation and optical transfer. Replace the legacy motif selectors with proportional `.finder`, `.incident-window`, and `.clip-strip` rules using percentages and `aspect-ratio`.

```css
.finder {
  position: absolute;
  inset-block-start: 0;
  inset-inline-start: 0;
  width: 28%;
  aspect-ratio: 1;
  background: var(--color-ink);
}
.finder::before, .finder::after { content: ""; position: absolute; }
.finder::before { inset: 13%; background: var(--color-paper); }
.finder::after { inset: 34%; background: var(--color-ink); }
.incident-window {
  position: absolute;
  inset-block: 0;
  inset-inline-end: 0;
  width: 32%;
  border: var(--rule-hairline) solid var(--color-ink);
  background:
    linear-gradient(var(--color-ink), var(--color-ink)) center / var(--rule-hairline) 64% no-repeat,
    linear-gradient(90deg, var(--color-ink), var(--color-ink)) center / 64% var(--rule-hairline) no-repeat;
}
.incident-window::after {
  content: "";
  position: absolute;
  inset-block-start: 39%;
  inset-inline-start: 39%;
  width: 22%;
  aspect-ratio: 1;
  background: var(--color-accent);
}
.clip-strip {
  position: absolute;
  inset-block-end: 0;
  inset-inline-start: 0;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  align-items: end;
  gap: 5%;
  width: 58%;
  aspect-ratio: 3 / 1;
}
.clip-strip span { position: relative; aspect-ratio: 1; border: var(--rule-hairline) solid var(--color-ink); }
.clip-strip span::after { content: ""; position: absolute; inset: 28%; background: var(--color-ink); }
.clip-strip span:nth-child(2) { border-color: var(--color-accent); background: var(--color-accent); }
.clip-strip span:nth-child(2)::after { background: var(--color-paper); }
```

- [ ] **Step 4: Verify automated behavior**

```bash
/Users/justin/Documents/ChatGPT/DashPi/.venv/bin/python -m pytest tests/test_landing.py -q
/Users/justin/Documents/ChatGPT/DashPi/.venv/bin/python -m pytest -q
npm test --prefix web
npm run build --prefix web
git diff --check
```

- [ ] **Step 5: Verify responsive rendering**

At 320, 375, 414, 768, and 1280 px, confirm no horizontal overflow and confirm the three motif elements retain identical normalized bounding boxes. Check Korean and English labels and browser errors.

- [ ] **Step 6: Commit and push main**

```bash
git add landing/index.html landing/styles.css tests/test_landing.py
git commit -m "feat: redesign landing hero motif"
git push origin main
```
