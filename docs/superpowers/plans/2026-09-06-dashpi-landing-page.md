# DashPi Landing Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and deploy a bilingual DashPi project landing page on GitHub Pages using the approved Hallmark Grid 01 visual system.

**Architecture:** Add an isolated static site under `landing/` so the marketing page cannot affect the packaged FastAPI UI in `src/dashpi/web/`. Use semantic HTML, one token stylesheet, one page stylesheet, and a small progressive-enhancement script; GitHub Actions publishes `landing/` directly as the Pages artifact.

**Tech Stack:** HTML5, CSS with OKLCH custom properties, vanilla JavaScript, Python stdlib `unittest`, GitHub Actions, GitHub Pages

## Global Constraints

- Keep the product runtime in `src/dashpi/web/` unchanged.
- Add no frontend framework, CSS framework, animation library, analytics, CMS, or package dependency.
- Default to Korean; provide a complete English translation and keep short English phrases visible in Korean mode.
- Use Hallmark Grid 01's exact paper, ink, rule, signal-red, Archivo, tracking, 12-column rail, ticker, and single-plate design system.
- Use `Noto Sans KR` only as the Hangul fallback because Archivo has no Hangul glyphs.
- Reuse only DashPi-owned images and copy no Hallmark logo, event copy, or exact geometric composition.
- Preserve Hallmark's MIT copyright and license notice in the deployed artifact.
- Make all technical claims traceable to `README.md`, `docs/PRD.md`, `docs/TRD.md`, or runnable tests.
- Do not call DashPi “open source” until the repository itself has a project license; use “View source on GitHub”.
- Preserve a useful Korean page when JavaScript is disabled or fails.
- Support keyboard use, visible focus, reduced motion, and widths 320, 375, 414, 768, and 1024px or larger without horizontal scrolling.

## File Map

- Create `landing/index.html` — semantic page structure, Korean default copy, embedded translation dictionary, metadata.
- Create `landing/tokens.css` — exact Grid theme colors, typography, spacing, easing, rules, and breakpoints.
- Create `landing/styles.css` — 12-column layout, hero geometry, ticker, index, plate, figures, tables, footer, responsive behavior.
- Create `landing/script.js` — language selection, translation application, safe persistence, ticker pause semantics.
- Create `landing/assets/icon.svg` — copy of `src/dashpi/web/icon.svg`.
- Create `landing/assets/dashpi-incidents.jpg` — copy of `docs/assets/dashpi-incidents.jpg`.
- Create `landing/assets/dashpi-optical-sender.jpg` — copy of `docs/assets/dashpi-optical-sender.jpg`.
- Create `landing/assets/dashpi-optical-receiver.jpg` — copy of `docs/assets/dashpi-optical-receiver.jpg`.
- Create `landing/THIRD_PARTY_NOTICES.md` — Hallmark MIT attribution and source links.
- Create `tests/test_landing.py` — stdlib-compatible static, translation, asset, and design-contract checks.
- Create `.github/workflows/pages.yml` — test and deploy the static artifact from `main`.

---

### Task 1: Semantic Korean Page and Owned Assets

**Files:**
- Create: `landing/index.html`
- Create: `landing/assets/icon.svg`
- Create: `landing/assets/dashpi-incidents.jpg`
- Create: `landing/assets/dashpi-optical-sender.jpg`
- Create: `landing/assets/dashpi-optical-receiver.jpg`
- Create: `landing/THIRD_PARTY_NOTICES.md`
- Create: `tests/test_landing.py`

**Interfaces:**
- Consumes: product claims from `README.md`, `docs/PRD.md`, and `docs/TRD.md`; existing DashPi visual assets.
- Produces: stable section IDs `top`, `flow`, `evidence`, `transfer`, `verification`, and `source`; `data-i18n` hooks consumed by Task 3.

- [ ] **Step 1: Write the failing structural test**

Create `tests/test_landing.py` with a stdlib parser so it runs under both `unittest` and the existing pytest suite:

```python
from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import json
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
LANDING = ROOT / "landing"


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.tags: list[str] = []
        self.assets: set[str] = set()
        self.i18n_keys: set[str] = set()
        self.i18n_attr_keys: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        self.tags.append(tag)
        if element_id := values.get("id"):
            self.ids.add(element_id)
        for name in ("src", "href"):
            value = values.get(name)
            if value and not value.startswith(("#", "http://", "https://", "mailto:")):
                self.assets.add(value)
        if key := values.get("data-i18n"):
            self.i18n_keys.add(key)
        if binding := values.get("data-i18n-attr"):
            self.i18n_attr_keys.add(binding.split(":", 1)[1])


class LandingPageTests(unittest.TestCase):
    def page(self) -> str:
        return (LANDING / "index.html").read_text(encoding="utf-8")

    def parser(self) -> PageParser:
        parser = PageParser()
        parser.feed(self.page())
        return parser

    def test_required_landmarks_sections_and_assets_exist(self) -> None:
        parser = self.parser()
        self.assertTrue({"header", "nav", "main", "section", "figure", "table", "footer"} <= set(parser.tags))
        self.assertTrue({"top", "flow", "evidence", "transfer", "verification", "source"} <= parser.ids)
        self.assertEqual(parser.tags.count("h1"), 1)
        for asset in parser.assets:
            self.assertTrue((LANDING / asset).is_file(), asset)

    def test_page_uses_dashpi_content_not_reference_content(self) -> None:
        page = self.page().lower()
        self.assertIn("dashpi", page)
        self.assertNotIn("signal, basel", page)
        self.assertNotIn("poster and graphic design festival", page)
```

- [ ] **Step 2: Run the test and verify the missing page failure**

Run:

```bash
python -m unittest discover -s tests -p 'test_landing.py'
```

Expected: ERROR because `landing/index.html` does not exist.

- [ ] **Step 3: Copy only the existing DashPi-owned assets**

Run:

```bash
mkdir -p landing/assets
cp src/dashpi/web/icon.svg landing/assets/icon.svg
cp docs/assets/dashpi-incidents.jpg landing/assets/dashpi-incidents.jpg
cp docs/assets/dashpi-optical-sender.jpg landing/assets/dashpi-optical-sender.jpg
cp docs/assets/dashpi-optical-receiver.jpg landing/assets/dashpi-optical-receiver.jpg
```

- [ ] **Step 4: Write the semantic Korean-first HTML**

Create `landing/index.html` with this document order:

```html
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DashPi — 인터넷 없이 사고 증거를 지키는 스마트 대시캠</title>
  <meta name="description" content="인터넷 없이 사고 영상을 보존하고 로컬 AI로 분석하는 오프라인 우선 스마트 대시캠 프로젝트입니다.">
  <meta name="theme-color" content="#fbfbfd">
  <meta property="og:type" content="website">
  <meta property="og:title" content="DashPi — Offline-first smart dashcam">
  <meta property="og:description" content="Understand and preserve an accident without depending on the cloud.">
  <meta property="og:image" content="assets/dashpi-incidents.jpg">
  <link rel="icon" href="assets/icon.svg" type="image/svg+xml">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700;800&amp;family=Noto+Sans+KR:wght@400;500;600;700;800&amp;display=swap" rel="stylesheet">
</head>
<body>
  <div class="rails" aria-hidden="true"></div>
  <header class="topbar" id="top">
    <div class="shell topbar__grid">
      <a class="wordmark" href="#top" aria-label="DashPi 홈">dashpi<span class="period" aria-hidden="true"></span></a>
      <nav class="topbar__nav" aria-label="페이지">
        <a href="#flow" data-i18n="nav.flow">작동 방식</a>
        <a href="#evidence" data-i18n="nav.evidence">실제 화면</a>
        <a href="#verification" data-i18n="nav.verification">검증</a>
        <a href="https://github.com/jcmaker/DashPi" data-i18n="nav.github">GitHub</a>
      </nav>
      <button class="language-toggle" type="button" aria-pressed="false" data-i18n-attr="aria-label:language.buttonLabel">EN</button>
    </div>
  </header>
  <main>
    <section class="hero" aria-labelledby="hero-title">
      <div class="shell hero__grid">
        <div class="hero__type">
          <h1 class="display" id="hero-title">dashpi<span class="period" aria-hidden="true"></span></h1>
          <p class="label" data-i18n="hero.description">인터넷 없이 사고 영상을 보존하고, 로컬 AI로 분석하는 스마트 대시캠</p>
          <p class="label" data-ko-only>Understand and preserve an accident without depending on the cloud.</p>
        </div>
        <div class="hero__composition" role="img" data-i18n-attr="aria-label:hero.artLabel">
          <!-- QR finder blocks, verification square, diagonal, and stepped bars; no copied Hallmark composition. -->
        </div>
      </div>
    </section>
    <div class="ticker" tabindex="0" data-i18n-attr="aria-label:ticker.label">
      <!-- Two identical runs for one continuous, pausable ticker. -->
    </div>
    <section class="flow" id="flow" aria-labelledby="flow-title">
      <!-- Four full-width index rows: capture, preserve, analyse, transfer. -->
    </section>
    <section class="plate" aria-labelledby="plate-title">
      <div class="shell plate__grid">
        <h2 id="plate-title" data-i18n="plate.title">AI가 실패해도, 증거는 남습니다.</h2>
        <p class="label" data-ko-only>Evidence survives even when analysis fails.</p>
      </div>
    </section>
    <section class="evidence" id="evidence" aria-labelledby="evidence-title">
      <!-- Three real product figures with honest captions. -->
    </section>
    <section class="transfer" id="transfer" aria-labelledby="transfer-title">
      <!-- Local Wi-Fi versus Optical QR semantic table. -->
    </section>
    <section class="verification" id="verification" aria-labelledby="verification-title">
      <!-- Completed software verification and pending hardware acceptance in separate ruled cells. -->
    </section>
    <section class="source" id="source" aria-labelledby="source-title">
      <h2 id="source-title" data-i18n="source.title">소스와 설계 문서 보기</h2>
      <a href="https://github.com/jcmaker/DashPi" data-i18n="source.cta">GitHub에서 DashPi 보기 ↗</a>
    </section>
  </main>
  <footer class="footer">
    <div class="shell footer__grid">
      <p class="label">DashPi · 2026</p>
      <a class="label" href="https://github.com/jcmaker/DashPi/blob/main/README.md">README</a>
      <a class="label" href="https://github.com/jcmaker/DashPi/blob/main/docs/PRD.md">PRD</a>
      <a class="label" href="THIRD_PARTY_NOTICES.md" data-i18n="footer.notices">Third-party notices</a>
    </div>
  </footer>
  <script id="translations" type="application/json">{"ko": {}, "en": {}}</script>
</body>
</html>
```

Fill every comment slot with the exact facts and labels from the approved design spec. Do not add testimonials, invented usage metrics, partner logos, pricing, or an online demo.

- [ ] **Step 5: Add the Hallmark MIT notice**

Create `landing/THIRD_PARTY_NOTICES.md` containing the source URLs followed by the complete license text from `https://github.com/Nutlope/hallmark/blob/main/LICENSE`, beginning:

```markdown
# Third-party notices

The visual system and portions of the CSS are adapted from Hallmark Grid 01:

- https://www.usehallmark.com/examples/grid-01/
- https://github.com/Nutlope/hallmark

MIT License

Copyright (c) 2026 Hallmark contributors
```

Include the complete permission, condition, and warranty paragraphs; do not abbreviate them.

- [ ] **Step 6: Run the structural test**

Run:

```bash
python -m unittest discover -s tests -p 'test_landing.py'
```

Expected: PASS.

- [ ] **Step 7: Commit the semantic page**

```bash
git add landing/index.html landing/assets landing/THIRD_PARTY_NOTICES.md tests/test_landing.py
git commit -m "feat: add DashPi landing page content"
```

---

### Task 2: Grid 01 Design System and Responsive Layout

**Files:**
- Create: `landing/tokens.css`
- Create: `landing/styles.css`
- Modify: `landing/index.html`
- Modify: `tests/test_landing.py`

**Interfaces:**
- Consumes: class names and section IDs from Task 1.
- Produces: exact CSS custom properties used by Task 3 state styles and a page that remains readable without JavaScript.

- [ ] **Step 1: Add failing design-contract tests**

Append to `LandingPageTests`:

```python
    def test_grid_theme_contract(self) -> None:
        tokens = (LANDING / "tokens.css").read_text(encoding="utf-8")
        styles = (LANDING / "styles.css").read_text(encoding="utf-8")
        expected_tokens = {
            "--color-paper": "oklch(99% 0.003 255)",
            "--color-ink": "oklch(16% 0.010 255)",
            "--color-rule": "oklch(88% 0.006 255)",
            "--color-accent": "oklch(55% 0.21 28)",
            "--font-display": '"Archivo", "Noto Sans KR", "Helvetica Neue", Arial, sans-serif',
        }
        for name, value in expected_tokens.items():
            self.assertIn(f"{name}: {value};", tokens)
        self.assertIn("repeat(12, minmax(0, 1fr))", styles)
        self.assertIn("overflow-x: clip", styles)
        self.assertIn("prefers-reduced-motion: reduce", styles)
        self.assertNotIn("box-shadow:", styles)
        self.assertNotIn("linear-gradient(135deg", styles)

    def test_stylesheets_are_linked(self) -> None:
        parser = self.parser()
        self.assertTrue({"tokens.css", "styles.css"} <= parser.assets)
```

- [ ] **Step 2: Run the tests and verify the missing stylesheet failure**

Run:

```bash
python -m unittest discover -s tests -p 'test_landing.py'
```

Expected: ERROR because `landing/tokens.css` and `landing/styles.css` do not exist.

- [ ] **Step 3: Write exact reusable tokens**

Create `landing/tokens.css` with the Hallmark stamps first, then the full token set:

```css
/* Hallmark · macrostructure: poster-index · theme: Grid · genre: editorial · tone: rational-institutional */
/* Hallmark · pre-emit critique: P4 H5 E4 S5 R4 V4 */
:root {
  --color-paper: oklch(99% 0.003 255);
  --color-paper-2: oklch(97.2% 0.003 255);
  --color-paper-3: oklch(94.5% 0.004 255);
  --color-ink: oklch(16% 0.010 255);
  --color-muted: oklch(43% 0.012 255);
  --color-rule: oklch(88% 0.006 255);
  --color-accent: oklch(55% 0.21 28);
  --color-accent-ink: var(--color-paper);
  --color-focus: var(--color-accent);
  --font-display: "Archivo", "Noto Sans KR", "Helvetica Neue", Arial, sans-serif;
  --font-body: "Archivo", "Noto Sans KR", "Helvetica Neue", Arial, sans-serif;
  --display-weight: 800;
  --tracking-display: -0.045em;
  --tracking-label: 0.09em;
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 16px;
  --space-4: 24px;
  --space-5: 32px;
  --space-6: 48px;
  --space-7: 64px;
  --space-8: 96px;
  --space-band: clamp(96px, 12vw, 152px);
  --gutter: clamp(16px, 2.5vw, 32px);
  --shell-max: 1280px;
  --dur-fast: 0.19s;
  --ease-out: cubic-bezier(0.22, 1, 0.36, 1);
  --rule-hairline: 1px;
  --rule-section: 2px;
  --radius-none: 0;
}
```

- [ ] **Step 4: Link the stylesheets**

Add these lines after the font stylesheet in `landing/index.html`:

```html
<link rel="stylesheet" href="tokens.css">
<link rel="stylesheet" href="styles.css">
```

- [ ] **Step 5: Implement the exposed grid and approved section rhythm**

Create `landing/styles.css`. Follow these exact layout contracts:

```css
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body { overflow-x: clip; }
html { scroll-behavior: smooth; }
body {
  background: var(--color-paper);
  color: var(--color-ink);
  font-family: var(--font-body);
  font-size: 16px;
  line-height: 1.5;
}
.rails {
  position: fixed;
  inset: 0;
  z-index: 0;
  max-width: var(--shell-max);
  margin-inline: auto;
  padding-inline: var(--gutter);
  background-clip: content-box;
  background-image: repeating-linear-gradient(to right,
    var(--color-rule) 0,
    var(--color-rule) var(--rule-hairline),
    transparent var(--rule-hairline),
    transparent calc(100% / 12));
  pointer-events: none;
}
.shell {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  max-width: var(--shell-max);
  margin-inline: auto;
  padding-inline: var(--gutter);
}
.display {
  font-family: var(--font-display);
  font-size: clamp(52px, 10.5vw, 136px);
  font-style: normal;
  font-weight: var(--display-weight);
  line-height: 0.9;
  letter-spacing: var(--tracking-display);
  overflow-wrap: anywhere;
}
.label {
  color: var(--color-muted);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: var(--tracking-label);
  text-transform: uppercase;
}
```

Implement all approved structures, keeping the source design's proportions:

- top bar: 1px ink rule; wordmark columns 1–5; nav columns 7–12.
- hero: 96px top and up to 160px bottom; copy columns 1–8; DashPi QR composition columns 8–12.
- ticker: one full-width ruled strip; 46-second linear loop; pause on hover and focus.
- flow: four full-width ruled rows; number column, title, metadata, one mark; 8px title slide on hover.
- plate: the only full red band; paper-colored copy and 15% paper rails; no radius or shadow.
- evidence: three shared ruled cells containing the real screenshots with `object-fit: cover` and visible captions.
- transfer: semantic spec table with tabular numbers and row hairlines.
- verification: two unequal grid cells, one for completed software and one for hardware acceptance still required.
- source/footer: one typographic CTA, then a sparse ruled footer.

Use one DashPi-specific geometric kit only: QR finder squares, hash blocks, a verification register, stepped transfer bars, border arrows, and one cropped `45` numeral for the 30+15-second incident window. Keep total non-plate accent area below 5% of a viewport.

- [ ] **Step 6: Add interaction states and responsive collapse**

Add visible default, hover, focus-visible, active, disabled, loading, error, and success selectors for the language button. Loading and success remain quiet; error keeps the Korean fallback visible.

```css
a:focus-visible,
button:focus-visible { outline: 2px solid var(--color-focus); outline-offset: 3px; }
.language-toggle:hover { color: var(--color-ink); }
.language-toggle:active { color: var(--color-accent); transform: translateY(1px); }
.language-toggle:disabled { color: var(--color-rule); cursor: not-allowed; }
.language-toggle[data-state="loading"] { color: var(--color-muted); }
.language-toggle[data-state="error"] { outline: 2px solid var(--color-accent); }
.language-toggle[data-state="success"] { border-bottom-color: var(--color-accent); }

@media (max-width: 60rem) {
  .hero__type, .hero__composition,
  .evidence__text, .evidence__figures,
  .transfer__text, .transfer__table,
  .verification__complete, .verification__pending { grid-column: 1 / 13; }
}

@media (max-width: 40rem) {
  .topbar__nav { display: none; }
  .hero { padding-block: var(--space-7); }
  .display { font-size: clamp(52px, 18vw, 80px); }
  .index__meta { display: none; }
  .evidence__figures { grid-template-columns: minmax(0, 1fr); }
  .footer__grid { display: flex; flex-direction: column; }
}

@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  *, *::before, *::after { transition-duration: 0.01ms !important; animation: none !important; }
}
```

- [ ] **Step 7: Run static tests**

Run:

```bash
python -m unittest discover -s tests -p 'test_landing.py'
python -m pytest -q tests/test_landing.py
```

Expected: both commands PASS.

- [ ] **Step 8: Commit the design system**

```bash
git add landing/index.html landing/tokens.css landing/styles.css tests/test_landing.py
git commit -m "feat: apply Grid design to landing page"
```

---

### Task 3: Bilingual Progressive Enhancement

**Files:**
- Modify: `landing/index.html`
- Create: `landing/script.js`
- Modify: `tests/test_landing.py`

**Interfaces:**
- Consumes: `data-i18n="key"`, `data-i18n-attr="attribute:key"`, `[data-ko-only]`, `.language-toggle`, and the embedded `#translations` JSON.
- Produces: `applyLanguage(language: "ko" | "en"): void`; updates `<html lang>`, visible copy, translated attributes, button state, and `localStorage["dashpi-language"]`.

- [ ] **Step 1: Add failing translation parity tests**

Append to `LandingPageTests`:

```python
    def translations(self) -> dict[str, dict[str, str]]:
        match = re.search(
            r'<script id="translations" type="application/json">(.*?)</script>',
            self.page(),
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        return json.loads(match.group(1))

    def test_translation_keys_match_and_cover_the_page(self) -> None:
        translations = self.translations()
        self.assertEqual(set(translations), {"ko", "en"})
        self.assertEqual(set(translations["ko"]), set(translations["en"]))
        parser = self.parser()
        referenced = parser.i18n_keys | parser.i18n_attr_keys
        self.assertLessEqual(referenced, set(translations["ko"]))
        self.assertTrue(all(translations[lang][key].strip() for lang in translations for key in translations[lang]))

    def test_script_has_safe_korean_fallback(self) -> None:
        script = (LANDING / "script.js").read_text(encoding="utf-8")
        self.assertIn('const DEFAULT_LANGUAGE = "ko";', script)
        self.assertIn("try", script)
        self.assertIn("localStorage", script)

    def test_script_is_linked(self) -> None:
        self.assertIn("script.js", self.parser().assets)
```

- [ ] **Step 2: Run the tests and verify the empty dictionary failure**

Run:

```bash
python -m unittest discover -s tests -p 'test_landing.py'
```

Expected: FAIL because the embedded `ko` and `en` dictionaries do not cover any `data-i18n` key and `script.js` is absent.

- [ ] **Step 3: Fill the complete translation dictionary**

In `landing/index.html`, replace the empty dictionaries with one flat dictionary per language. Use the same keys in both locales, including:

```json
{
  "ko": {
    "language.buttonLabel": "영어로 보기",
    "nav.flow": "작동 방식",
    "nav.evidence": "실제 화면",
    "nav.verification": "검증",
    "nav.github": "GitHub",
    "hero.description": "인터넷 없이 사고 영상을 보존하고, 로컬 AI로 분석하는 스마트 대시캠",
    "hero.artLabel": "광학 QR 전송과 무결성 검증을 표현한 기하학 구성",
    "ticker.label": "DashPi 핵심 원칙과 기술",
    "plate.title": "AI가 실패해도, 증거는 남습니다.",
    "source.title": "소스와 설계 문서 보기",
    "source.cta": "GitHub에서 DashPi 보기 ↗",
    "footer.notices": "외부 저작권 고지"
  },
  "en": {
    "language.buttonLabel": "한국어로 보기",
    "nav.flow": "How it works",
    "nav.evidence": "Product views",
    "nav.verification": "Verification",
    "nav.github": "GitHub",
    "hero.description": "A smart dashcam that preserves accident footage and analyses it with local AI—without the internet",
    "hero.artLabel": "Geometric composition representing optical QR transfer and integrity verification",
    "ticker.label": "DashPi principles and technologies",
    "plate.title": "Evidence survives even when analysis fails.",
    "source.title": "Explore the source and design documents",
    "source.cta": "View DashPi on GitHub ↗",
    "footer.notices": "Third-party notices"
  }
}
```

Add equivalent keys for every remaining section heading, paragraph, index row, table heading/cell, figure caption/alt text, verification item, link, and mobile-menu label. Do not leave any visible Korean string in English mode except the language button text `한국어`.

- [ ] **Step 4: Link and implement the language controller**

Add `<script src="script.js" defer></script>` after the stylesheets in `landing/index.html`, then create `landing/script.js`:

```javascript
const DEFAULT_LANGUAGE = "ko";
const STORAGE_KEY = "dashpi-language";
const toggle = document.querySelector(".language-toggle");
const dictionaryNode = document.querySelector("#translations");

function storedLanguage() {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return value === "en" || value === "ko" ? value : DEFAULT_LANGUAGE;
  } catch {
    return DEFAULT_LANGUAGE;
  }
}

function saveLanguage(language) {
  try {
    localStorage.setItem(STORAGE_KEY, language);
  } catch {
    // The page still works for this session when storage is unavailable.
  }
}

function applyLanguage(language) {
  const locale = language === "en" ? "en" : DEFAULT_LANGUAGE;
  const messages = translations[locale] || translations[DEFAULT_LANGUAGE];
  toggle.dataset.state = "loading";

  document.querySelectorAll("[data-i18n]").forEach((node) => {
    const value = messages[node.dataset.i18n] ?? translations[DEFAULT_LANGUAGE][node.dataset.i18n];
    if (value) node.textContent = value;
  });
  document.querySelectorAll("[data-i18n-attr]").forEach((node) => {
    const [attribute, key] = node.dataset.i18nAttr.split(":", 2);
    const value = messages[key] ?? translations[DEFAULT_LANGUAGE][key];
    if (attribute && value) node.setAttribute(attribute, value);
  });

  document.documentElement.lang = locale;
  document.querySelectorAll("[data-ko-only]").forEach((node) => { node.hidden = locale !== "ko"; });
  toggle.textContent = locale === "ko" ? "EN" : "한국어";
  toggle.setAttribute("aria-pressed", String(locale === "en"));
  saveLanguage(locale);
  requestAnimationFrame(() => { toggle.dataset.state = "success"; });
}

let translations;
try {
  translations = JSON.parse(dictionaryNode.textContent);
  toggle.addEventListener("click", () => applyLanguage(document.documentElement.lang === "ko" ? "en" : "ko"));
  applyLanguage(storedLanguage());
} catch {
  toggle.dataset.state = "error";
  toggle.disabled = true;
}
```

- [ ] **Step 5: Run translation and full project tests**

Run:

```bash
python -m unittest discover -s tests -p 'test_landing.py'
python -m pytest -q
npm test --prefix web
```

Expected: landing, Python, and TypeScript suites PASS.

- [ ] **Step 6: Commit bilingual behavior**

```bash
git add landing/index.html landing/script.js tests/test_landing.py
git commit -m "feat: add Korean and English landing copy"
```

---

### Task 4: GitHub Pages Workflow and Browser Verification

**Files:**
- Create: `.github/workflows/pages.yml`
- Modify: `tests/test_landing.py`

**Interfaces:**
- Consumes: the complete `landing/` directory and `tests/test_landing.py` from Tasks 1–3.
- Produces: a Pages deployment artifact rooted at `landing/index.html` and a workflow triggered by relevant `main` changes.

- [ ] **Step 1: Add a failing deployment-contract test**

Append to `LandingPageTests`:

```python
    def test_pages_workflow_publishes_landing_directory(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
        self.assertIn("actions/configure-pages@v5", workflow)
        self.assertIn("actions/upload-pages-artifact@v3", workflow)
        self.assertIn("actions/deploy-pages@v4", workflow)
        self.assertIn("path: landing", workflow)
        self.assertIn("pages: write", workflow)
        self.assertIn("id-token: write", workflow)
```

- [ ] **Step 2: Run the test and verify the missing workflow failure**

Run:

```bash
python -m unittest discover -s tests -p 'test_landing.py'
```

Expected: ERROR because `.github/workflows/pages.yml` does not exist.

- [ ] **Step 3: Create the Pages workflow**

Create `.github/workflows/pages.yml`:

```yaml
name: Deploy landing page

on:
  push:
    branches: [main]
    paths:
      - landing/**
      - tests/test_landing.py
      - .github/workflows/pages.yml
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: true

jobs:
  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Verify landing page
        run: python -m unittest discover -s tests -p 'test_landing.py'
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: landing
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
```

- [ ] **Step 4: Run all automated checks**

Run:

```bash
git diff --check
python -m unittest discover -s tests -p 'test_landing.py'
python -m pytest -q
npm test --prefix web
npm run build --prefix web
```

Expected: no whitespace errors; all Python and TypeScript tests PASS; the TypeScript build succeeds.

- [ ] **Step 5: Serve the landing page locally**

Run:

```bash
python -m http.server 4173 --directory landing
```

Open `http://127.0.0.1:4173/` and keep the server running only for the verification steps.

- [ ] **Step 6: Verify the approved page behavior**

At desktop width, verify:

- the visible 12-column rails align with the content shell;
- Archivo renders Latin text and Noto Sans KR renders Hangul;
- the Hero is left-biased and contains no CTA;
- exactly one ticker and one signal-red plate exist;
- the three images are real DashPi captures without fake browser chrome;
- `EN` translates all visible page content and changes `<html lang>` to `en`;
- reloading preserves the selected language;
- keyboard focus is visible and the ticker pauses when focused.

At 320, 375, 414, 768, and 1024px widths, verify:

- `document.documentElement.scrollWidth === window.innerWidth`;
- no heading, CTA, nav link, footer link, or table cell overlaps or clips;
- all clickable controls are at least 44px high at phone widths;
- split sections stack in the intended reading order;
- screenshots preserve aspect ratio and remain inside their grid tracks.

With reduced motion enabled, verify the ticker and geometric transforms do not animate.

- [ ] **Step 7: Run the Hallmark post-build review**

Load `hallmark/references/slop-test.md` only now and run all 58 gates. Fix every failure before continuing. Confirm the artifact begins with the Hallmark macrostructure and pre-emit critique stamps, contains no invented metrics, no cards, no gradients, no shadows, no rounded surfaces, no second accent color, and no second plate.

- [ ] **Step 8: Commit deployment support**

```bash
git add .github/workflows/pages.yml tests/test_landing.py
git commit -m "ci: deploy landing page to GitHub Pages"
```

- [ ] **Step 9: Push and enable GitHub Pages**

Push `main`, then in the repository's GitHub Pages settings select **GitHub Actions** as the source if it is not already selected. Confirm the workflow reports the deployed URL and that `https://jcmaker.github.io/DashPi/` loads the same checked artifact.

This external configuration step requires the repository owner's authenticated GitHub session; the code change is complete even if the setting still needs to be selected manually.
