# Drop source assets here. Suggested files:

- `hero-mountain.jpg` — hero background (2044×1084 source, optimized AVIF/WebP preferred)
- `portrait.jpg` — founder portrait (147×221 source)
- `logo.svg` — Merimee Digital Solutions monogram
- `og/home.png` — 1200×630 social card
- `projects/holy-rollers.jpg`
- `projects/chesterton.jpg`
- `projects/parker-eidle.jpg`
- `projects/alena-carter.jpg`
- `projects/bonfire.jpg`

The wixstatic.com originals in `SiteUnderstanding.images` should be re-exported
at higher resolution before being committed here. Until then, the build still
serves cleanly with the `/images/...` paths (Next/Image will 404 the missing
files, but the page is fully typed and the components render their text/CTA).
