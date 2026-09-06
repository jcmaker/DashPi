# DashPi Open Graph image

## Goal

Replace the current application screenshot preview with a dedicated 1200×630 DashPi social card based on the approved dark-tech direction B.

## Image design

- Use a near-black background, white `dashpi` wordmark, and the existing red accent square.
- Set the main message in large white type: `ACCIDENT EVIDENCE.` and `OFFLINE FIRST.`
- Add the compact technical line `LOCAL AI / SHA-256 / RASPBERRY PI` in red monospace text.
- Place one oversized rotated red outline/signal form partially outside the lower-right edge for depth.
- Keep generous empty space and high contrast so the card remains legible in small link previews.
- Produce a deterministic 1200×630 PNG. Do not use a runtime image service or add a dependency.

## Metadata

- Replace the current `dashpi-incidents.jpg` Open Graph image with the new absolute PNG URL.
- Add image type, width, height, and alt metadata.
- Add `og:url`, `og:site_name`, a canonical URL, and matching `twitter:card`, title, description, image, and image-alt metadata.
- Keep the existing English Open Graph title and description.

## Scope

Modify or create only:

- `landing/assets/dashpi-og.svg` as the editable source
- `landing/assets/dashpi-og.png` as the published asset
- `landing/index.html`
- `tests/test_landing.py`

## Verification

- Add a test that reads the PNG header and asserts exact 1200×630 dimensions.
- Add metadata assertions for the absolute image URL, dimensions, alt text, canonical URL, and large Twitter card.
- Run the landing tests, full Python and web test suites, web build, `git diff --check`, and inspect the generated PNG visually.
