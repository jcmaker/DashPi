# Clearbox solid ASCII footer

## Goal

Honor DashPi's original name, Clearbox, with a solid, character-shaded rotating cube. The rendering approach follows the supplied `interactive-artwork` reference's idea of sampling a 3D surface and mapping light to glyphs, but uses a cube and the existing dependency-free landing stack.

## Layout

- Treat the entire footer as one dark, full-width closing panel.
- Place `ORIGIN / CLEARBOX`, the origin statement, and its supporting sentence on the left.
- Place a large solid monospace cube on the right, filled with different glyphs for the visible faces rather than drawn as an outline.
- Keep the existing copyright and README, PRD, TRD, and notice links in the lower strip, but make that strip part of the same dark footer with a subdued separating rule.
- Collapse the origin copy and cube into one column on narrow screens without horizontal overflow.

## Copy

Korean:

```text
ORIGIN / CLEARBOX
DashPi는 Clearbox에서 시작되었습니다.
사고 직후의 혼란을, 더 명확한 기록과 전달로 바꾸기 위한 첫 이름이었습니다.
```

English:

```text
ORIGIN / CLEARBOX
DashPi began as Clearbox.
It was our first name for turning the confusion after a crash into a clearer record and handoff.
```

## Solid cube rendering and motion

- Render one `<pre>` element with a filled, character-shaded static cube as the no-JavaScript fallback.
- Generate each frame by casting a small fixed grid of rays at a rotated cube, selecting the nearest face, and mapping that face's light value to a short ASCII shade ramp.
- Use the existing `requestAnimationFrame` loop with a low frame rate and time-based rotation. Do not add canvas, WebGL, dependencies, controls, or keyboard interaction.
- Render one stable solid frame when `prefers-reduced-motion: reduce` is active.
- Mark the cube decorative with `aria-hidden="true"`; the adjacent origin copy carries the meaning.

## Visual system

- Preserve the existing Grid theme, Archivo/Noto Sans KR typography, spacing tokens, and red accent.
- Use existing paper and ink tokens for the full dark footer and its foreground; add no new colour values.
- Add one `--font-mono` token using the system monospace fallback stack; do not load another font.
- Keep animation subordinate to the origin statement.

## Scope

Modify only:

- `landing/index.html`
- `landing/tokens.css`
- `landing/styles.css`
- `landing/script.js`
- `tests/test_landing.py`

No files are deleted and no unrelated section changes.

## Verification

- Add focused regression coverage for the origin copy, semantic footer structure, solid renderer output, static fallback, and reduced-motion guard.
- Verify Korean and English content in the browser.
- Verify no horizontal overflow at 320, 375, 414, 768, and desktop widths.
- Run the full Python and web test suites, web build, and `git diff --check`.
