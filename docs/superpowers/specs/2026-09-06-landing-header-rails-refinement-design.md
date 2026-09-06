# Landing Header and Rails Refinement

## Goal

Keep the existing Hallmark Grid landing design while fixing two visual hierarchy issues:

- The wordmark and language control must share one header row at every supported width.
- The vertical grid rails must remain visible at every width, but read as a quiet background guide rather than foreground structure.

## Design

The header keeps its existing 12-column grid. At the tablet and mobile breakpoint, the controls begin after the wordmark instead of overlapping its columns; this prevents CSS Grid auto-placement from moving the controls to a second row.

The rails receive a dedicated low-contrast colour token instead of reusing the stronger divider token. Header, main content, and footer establish an explicit layer above the fixed rails. Section borders and other rules keep their current contrast.

## Scope

- Update `landing/tokens.css` with one rail colour token.
- Update `landing/styles.css` for rail colour, page stacking, and the header breakpoint column.
- Extend `tests/test_landing.py` with a small CSS contract test.
- Do not change markup, copy, spacing, typography, animation, or dependencies.

## Verification

- Run the landing test suite and the full Python suite.
- Verify the static page at 320, 375, 414, and 768 px with no horizontal overflow.
- Confirm the wordmark and language control share the same row in Korean and English.
- Confirm the rails remain visible but lower contrast than section rules.
