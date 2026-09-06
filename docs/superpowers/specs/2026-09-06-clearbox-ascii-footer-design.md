# Clearbox ASCII footer

## Goal

Honor DashPi's original name, Clearbox, with a restrained origin panel inspired by the GitHub Shop footer's rotating ASCII cube without copying its implementation or full visual system.

## Layout

- Expand the footer with a dark, full-width origin panel above the existing document-link strip.
- Place `ORIGIN / CLEARBOX`, the origin statement, and its supporting sentence on the left.
- Place a large monospace ASCII cube on the right.
- Keep the existing copyright and README, PRD, TRD, and notice links in their current light lower strip.
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

## ASCII cube motion

- Render one `<pre>` element with a readable static cube as the no-JavaScript fallback.
- Cycle through a small fixed array of hand-authored ASCII frames with the existing `landing/script.js`; do not add a canvas, WebGL, dependency, control, or keyboard interaction.
- Advance slowly with `requestAnimationFrame`, changing only text content at fixed intervals.
- Stop on a stable first frame when `prefers-reduced-motion: reduce` is active.
- Mark the cube decorative with `aria-hidden="true"`; the adjacent origin copy carries the meaning.

## Visual system

- Preserve the existing Grid theme, Archivo/Noto Sans KR typography, spacing tokens, and red accent.
- Use existing paper and ink tokens for the dark panel and its foreground; add no new colour values.
- Use the existing monospace fallback stack for the ASCII drawing.
- Keep animation subordinate to the origin statement.

## Scope

Modify only:

- `landing/index.html`
- `landing/styles.css`
- `landing/script.js`
- `tests/test_landing.py`

No files are deleted and no unrelated section changes.

## Verification

- Add focused regression coverage for the origin copy, semantic footer structure, ASCII fallback, and reduced-motion guard.
- Verify Korean and English content in the browser.
- Verify no horizontal overflow at 320, 375, 414, 768, and desktop widths.
- Run the full Python and web test suites, web build, and `git diff --check`.
