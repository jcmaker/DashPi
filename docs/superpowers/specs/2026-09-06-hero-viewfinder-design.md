# Hero Recording Viewfinder Redesign

## Goal

Replace the current incident motif with a text-free camera viewfinder that immediately communicates video recording while retaining the same proportions at every viewport width.

This specification supersedes `2026-09-06-hero-incident-motif-design.md` for the hero artwork only.

## Reference Principles

- Use the familiar open-corner framing language found in camera focus and crop interfaces, including Material Symbols' `center_focus_strong` family.
- Use a solid red circular indicator as the recording cue.
- Keep the indicator static because the hero is explanatory artwork, not a live recording status display.
- Avoid `REC` text so the artwork remains language-independent and does not reintroduce a badge.

References:

- Material Symbols focus icon: <https://fonts.google.com/icons?selected=Material+Symbols+Outlined:center_focus_strong:FILL@0;wght@400;GRAD@0;opsz@24>
- W3C Media Capture privacy and recording indicator considerations: <https://www.w3.org/TR/mediacapture-streams/#privacy-and-security-considerations>

## Visual Design

- Keep the existing hero composition's `5 / 3` aspect ratio and grid placement.
- Draw four open corner brackets around the composition instead of a closed rectangular border.
- Place a small red circular recording indicator near the upper-left corner.
- Place a thin rectangular focus window in the centre.
- Place a small red square at the centre of the focus window to represent the captured incident moment and retain DashPi's square brand accent.
- Use only the existing paper, ink, rule, and accent colour tokens.
- Do not animate the artwork.

## Responsive Behaviour

- Define all geometric positions and component dimensions as percentages of the existing hero composition.
- Retain `aspect-ratio` for the composition and both accent marks.
- Use the existing hairline rule token for stroke thickness so corners and the focus window stay legible.
- Do not add breakpoint-specific viewfinder geometry.
- Keep strokes visually legible without allowing them to dominate at mobile or desktop widths.

## Accessibility

- The composition remains one `role="img"` element.
- Decorative children remain hidden with `aria-hidden="true"`.
- Korean label: `영상 녹화와 사고 시점 포착을 표현한 카메라 뷰파인더`
- English label: `Camera viewfinder representing video recording and incident capture`

## Scope

- Modify `landing/index.html`, `landing/styles.css`, and `tests/test_landing.py` only.
- Remove the current `.finder`, `.incident-window`, and `.clip-strip` motif markup and styles.
- Add no dependency and no JavaScript.
- Do not change landing copy, the statement section, the footer, or any other section.

## Verification

- The old motif selectors and markup no longer exist.
- The new viewfinder, recording indicator, and focus window exist in HTML and CSS.
- Korean and English language modes expose the updated accessible label.
- At 320, 375, 414, 768, 1280, and 1920 CSS pixels, the page has no horizontal overflow and the viewfinder elements retain identical normalised bounding boxes.
- The landing tests, full Python suite, web tests, web build, and `git diff --check` pass.
