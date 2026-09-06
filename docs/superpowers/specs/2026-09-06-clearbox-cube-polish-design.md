# Clearbox cube motion and shading polish

## Goal

Make the solid Clearbox cube feel more alive and legible without changing the footer layout or adding dependencies.

## Design

- Animate the existing `.footer__cube` foreground from paper white to the existing DashPi red accent and back with one smooth CSS keyframe cycle.
- Keep the colour cycle decorative and disable it with the page's existing `prefers-reduced-motion: reduce` rule.
- Retain the current ray-cast cube renderer, but replace the short shade ramp with a longer ASCII ramp and use a small deterministic screen-space dither when selecting adjacent glyphs. This creates visible variation within flat faces while preserving the solid silhouette.
- Increase the rotation multiplier from a roughly 42-second revolution to roughly 30 seconds. Keep the current low render cap so the decoration stays lightweight.
- Do not add controls, per-character DOM nodes, canvas, WebGL, new colour tokens, or dependencies.

## Scope

Modify only:

- `landing/styles.css`
- `landing/script.js`
- `tests/test_landing.py`

## Verification

- Add focused regression assertions for the white-to-red CSS cycle, richer glyph output, faster rotation multiplier, and reduced-motion behavior.
- Run the landing tests first, then the full Python and web test suites, web build, JavaScript syntax check, and `git diff --check`.
- Confirm the local preview still has no horizontal overflow and the cube remains readable at desktop and mobile widths.
