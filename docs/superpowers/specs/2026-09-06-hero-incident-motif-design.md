# Hero Incident Motif Redesign

## Goal

Replace the hero's SHA-256 badge and existing lower ornament with a text-free composition that represents DashPi's incident workflow while retaining its shape at every viewport width.

## Visual Design

- Keep the existing optical finder at the upper left as the transfer cue.
- Replace the SHA badge with a three-frame incident sequence: before, red trigger moment, and after.
- Replace the descending bars with a compact three-cell clip strip.
- Build every major dimension from percentages and `aspect-ratio`; do not use breakpoint-specific motif geometry.
- Keep the existing black, paper, and red token palette and the current hero layout.

## Scope

- Modify `landing/index.html`, `landing/styles.css`, and `tests/test_landing.py` only.
- Update the Korean and English accessible labels to describe incident preservation and optical transfer.
- Do not change landing copy, the red statement section, footer content, dependencies, or other sections until the user supplies the revised capstone narrative.

## Verification

- The SHA badge markup and its CSS selector no longer exist.
- The new motif remains proportional without horizontal overflow at 320, 375, 414, 768, and desktop widths.
- Korean and English language modes expose the updated accessible label.
