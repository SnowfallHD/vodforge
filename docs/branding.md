# Approved matte VF branding

The user approved the extended-F matte artwork in
[the original reference](references/approved-vf-matte-logo.png).
The rich mark must retain its original texture, sculpted shading, geometry and
muted lavender material. The rejected polygon reconstruction is not a master.
The current statement is **Your media. Your way.**

Canonical source SHA-256:
4ea899554339f84c07366c2aa511b03fc96a077aab199a66c4779f50cd595c7f.

Run from the desktop checkout, using Pillow:
    python scripts/export_brand.py --font /path/to/Arial.ttf --site /path/to/vodforge-site-checkout

The optional site argument copies assets only; it does not deploy. Font is used
only for the tagline in the social card, and its digest is recorded. The rich
wordmark and mark are original source pixels, not newly typeset or vectorized.
The exporter checks the source hash, crops exact regions, removes background
through alpha only, and proportionally resizes for platform containers. Opaque
and transparent RGB values are unchanged in the extracted masters. The app tile
adds platform margin outside the extracted tile. No AI regeneration or artwork
redrawing occurs in this export pipeline.

assets/brand/manifest.json records input/crop provenance and output hashes.
The source tile is 588x588 pixels; the 1024 platform export is an upscale, not new
detail. Original reference and extracted master pixels remain available.
assets/VODForge.icns includes Retina sizes; VODForge.ico includes 16 through 256.
The desktop header pairs vf-mark.png with vf-name.png and retains its compact mark-only behavior. The site uses the original combined vf-wordmark.png.
Both build scripts include assets/brand. Website header, email mark, social card,
favicon and webmanifest use these exports. Historical product screenshots are
not edited to fake a newly installed app; refresh them from qualified builds.

Verify with tests/test_brand_assets.py and native tests/test_brand_native.py,
then inspect small-size sheets and the actual website at desktop/mobile widths.
Native, site-preview, packaged and installed icon acceptance remain distinct.
Existing engineering gates and unresolved resize acceptance are not waived.


The social preview alone is monochromatic. It uses the larger approved mark
crop, downsampled to 225x197, and the original name at its native 489x108
resolution. Neither is enlarged. Grayscale preserves the source shading and
texture; a 0.3px alpha blur softens extraction edges. The original lavender
masters remain unchanged. Avoid enlarging the smaller combined lockup for the
social card, which previously produced softened detail and rough mask edges.
The asset regression also verifies that all social-preview RGB channels match.

ICNS representations use Pillow's default bicubic resizing and are checked by
RGBA round-trip regression against the export master. Source tile is 588x588;
872px artwork within the 1024 canvas is an upscale. Container fidelity does not
establish installed Dock acceptance.

September 19: theme-specific app and site derivatives are now explicitly authorized.
They preserve approved geometry/alpha and material luminance, with monochrome
palette tint. This does not change canonical raster masters or platform icon exports.
