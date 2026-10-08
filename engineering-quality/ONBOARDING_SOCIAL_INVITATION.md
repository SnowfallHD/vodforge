# Optional welcome and social invitation

Current Qt first-run onboarding presents one compact screen using the canonical logo, existing theme/surfaces, three bundled product previews, one headline and a Get started action. Optional Follow @VODForge opens the existing public X URL only after activation. The existing six-page Help welcome tour remains available; other screens and controls are unchanged.

Existing users receive one separate support/update invitation after higher-priority welcome, rating and release announcements settle, and only after eight seconds of UI idle. Window pointer, keyboard and wheel input resets the idle interval; held presses and downloads, queued work, playback, consent and other open popups defer it. No input logs are collected. Not now, Escape and explicit Follow persist dismissal in the existing settings store. First-run welcome includes the invitation and records that receipt, preventing a duplicate upgrade invitation immediately after it.

The generated concept supplied by the user establishes layout, not branding. Its pixel materialization failed HTTP403; extracted text and the parent's layout description were available. Actual VODForge offscreen renders were visually inspected. No generic play logo or global light theme was introduced.

Qualification: 57 selected editorial/social/welcome/shared-popup cases passed after correcting a new invitation timing regression (earlier shared-popup run:7 failures). Final full orientation/social module:20 passed, including actual fresh-profile eligibility and settings reload. Ruff, format and diff checks pass. Existing Qt module remains enrolled in Mac/CI partitions. Native candidate/browser opening and OS capture remain separate; source render is not frozen/native evidence.

A new runtime build and focused frozen/package checks are required. RC5 and the prior stable-version build remain preserved. No social post, auto-follow, support gate, ordinary installation or global styling change is part of this patch.

## Requested preview visual revision

Remove the added rounded preview rectangles and their borders. Three direct Image delegates now show the existing committed 2200×1480 native source captures in assets/readme/current-design (library.png, watch.png, player.png), rather than the 960×646 recorded-preview posters. Each preview grows from a 114×70 inner image to 176×122 logical image bounds; aspect-fit retains the complete app frame and the existing slight outer rotations. Decode at 880×592 from the 2200×1480 originals, providing enough source detail for native 2x display without enlarging a low-resolution poster. Both packaging scripts explicitly include those existing PNG files; no new screenshot asset or external content is introduced.

Remove the Following is optional footer text; retain Get started and the explicit optional X action. No control is relocated outside onboarding, no shared hit area/functionality is changed, and no additional hierarchy redesign lands elsewhere. Existing focused orientation/social tests: 20 passed. The actual revised source UI was rendered and inspected offscreen at 2200×1480; this is review evidence, not a replacement native frozen recording. A new private package and continuous native first-run recording must follow once this visual revision is finalized. Previous 8929b67 artifacts and recordings remain preserved.
