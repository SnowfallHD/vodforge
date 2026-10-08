# Optional welcome and social invitation

Current Qt first-run onboarding presents one compact screen using the canonical logo, existing theme/surfaces, three bundled product previews, one headline and a Get started action. Optional Follow @VODForge opens the existing public X URL only after activation. The existing six-page Help welcome tour remains available; other screens and controls are unchanged.

Existing users receive one separate support/update invitation after higher-priority welcome, rating and release announcements settle, and only after eight seconds of UI idle. Window pointer, keyboard and wheel input resets the idle interval; held presses and downloads, queued work, playback, consent and other open popups defer it. No input logs are collected. Not now, Escape and explicit Follow persist dismissal in the existing settings store. First-run welcome includes the invitation and records that receipt, preventing a duplicate upgrade invitation immediately after it.

The generated concept supplied by the user establishes layout, not branding. Its pixel materialization failed HTTP403; extracted text and the parent's layout description were available. Actual VODForge offscreen renders were visually inspected. No generic play logo or global light theme was introduced.

Qualification: 57 selected editorial/social/welcome/shared-popup cases passed after correcting a new invitation timing regression (earlier shared-popup run:7 failures). Final full orientation/social module:20 passed, including actual fresh-profile eligibility and settings reload. Ruff, format and diff checks pass. Existing Qt module remains enrolled in Mac/CI partitions. Native candidate/browser opening and OS capture remain separate; source render is not frozen/native evidence.

A new runtime build and focused frozen/package checks are required. RC5 and the prior stable-version build remain preserved. No social post, auto-follow, support gate, ordinary installation or global styling change is part of this patch.

## Final preview and hierarchy revision

Three direct Image delegates replace the decorative rounded preview containers and borders. Library, Watch and Forge previews use fresh 2200×1480 QQuickWindow.grabWindow captures of the actual source UI, rendered at 2x in an isolated fictional nature-media profile. The complete app-window content is retained; there is no desktop capture, computer-use overlay, white background corner, generated replacement, pixel masking or low-resolution enlargement. The committed assets live in assets/onboarding and both platform packaging scripts include all three. Each preview uses 176×122 logical bounds, aspect-fit, the existing rotations and an 880×592 decode target. These source renders are review evidence, not frozen/native acceptance.

The Following is optional footer is removed. Get started and the explicit X action remain. Outside onboarding, the hierarchy pass changes only three text colors: compact Library counts use the primary text color, the composer Save to label uses the primary text color, and Watch creator metadata uses the muted color shared by the other metadata. Fonts, dimensions, positions, hit areas, focus and behavior are unchanged.

Before/after Forge, Library and Watch window renders are preserved in the owner's hierarchy-evidence directory. All three full-resolution assets and the corrected onboarding composite were visually inspected. Focused welcome/social, Library selection placement, Watch hero refresh and composer feedback tests passed: 46 cases. Previous 8929b67 packages and recordings remain preserved. A new private package, frozen checks and native continuous first-run recording must qualify this exact successor; earlier acceptance must not be relabeled.
