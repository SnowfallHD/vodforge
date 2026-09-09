# Analytics journey evidence — 2026-09-07

> Historical, checkpoint-specific receipts. Timing and focus observations below
> are not guarantees for every OS/browser or proof for a newer build. Current
> behavior and state ownership are described in [architecture](../docs/architecture.md#privacy-and-onboarding-state).

## Earlier native activation — 2026-09-08

- Production checkpoint `46fc72691c95134430e91651886f60f431fc33d2` reduces
  prompt-to-handoff scheduling from 300 + 400 ms to 50 + 100 ms. Browser-return
  polling retains its bounded 1.5-second budget. Dismissed/answered prompts
  still cancel the request; no activation loop or extra browser tab is added.
- macOS uses `NSApplication.activate()` on current systems, with the older API
  only where that selector is unavailable. Fresh ad-hoc packaged preview passed
  runtime/signature checks. `build/preview-journeys/sooner-mac-DE/startup-journey.json`
  records prompt visibility at 1.690 s, native request at 1.746 s, and actual OS
  foreground at 1.898 s. The immediate `accepted: false` is the synchronous
  `isActive()` observation before asynchronous activation, not a rejection.
- Windows prior installed run 21 records native `SetForegroundWindow` returning
  false inside VODForge. A later call by the QA parent process succeeded. The
  separate same-process Tk spike found later retries, BringWindowToTop,
  SetWindowPos(TOP), ShowWindow, and SetActiveWindow did not activate the app.
  Do not conflate successful Z-order calls or test-only raises with activation.
- Windows retains the one native wrapper request and now uses three finite
  taskbar flashes if refused. This does not report foreground success, attach
  input queues, synthesize keys, or leave the app always on top.
- Exact-checkpoint FAST gate passed at
  `reports/20260908T084352195529Z-46fc7269-fast/fast-gate.json`.
- Windows installed follow-up run `20260908000000000000000000000022` matches
  executable SHA256 `a9915ee7f6f444eea912dd161fc6e585c8a5f37233363ac52ed5bdf835d273ce`.
  Native request occurred at app-relative 1.626 s, after adapter return at
  1.223 s (Tk work adds latency beyond the configured grace). Windows refused
  activation; actual OS foreground remained Brave at 1.797 s. The later
  QA-parent activation succeeded. Visual pass is not automatic-focus pass.
  The shortened request, centered four-band panel, black scrim and clean exit
  passed. No public release signing, production telemetry or user Mac app
  replacement is included.

## Preview D1 packaged matrix — 2026-09-08 final follow-up

This is **preview**, not production, release-signing, or HeyCatch certification.
Database `vodforge_preview` (`924640fb-3be3-47ca-992c-1c7745bd8469`) has migrations
0001–0010. The deployed preview Worker is
`849bc20e-c719-4322-ab82-5e7f1f767924`. Private QA key/profile gates remain required.
No ordinary replacement build was enabled for production telemetry.

### Artifact provenance

- macOS arm64: `bd23274a86a9e46f23a0539af006ae8d82b35154`, built as preview
  version 0.1.8, ad-hoc signed, runtime smoke and strict signature verification
  passed. Fresh DMG mount/copy is `build/preview-focus-dmg-installed/VODForge.app`.
- Windows x64 final base/visual matrix: `e2f28404ad22d725222baf2c6703caa48fcdb3c0`;
  executable SHA256 `43d688ca74d734f81692f713e8becf234bc717bf0638f6a4a796ac9d68abf3c7`.
  Real Inno installer into `E:\VODForgeQA\installed\VODForge`, plus freshly
  zipped/extracted portable. Both are unsigned QA artifacts, not public releases.
- Windows real-clock extended matrix used the preceding `bd23274` artifact
  (`cfb09dfb355de245d2eb1f7db3839e4809e504178dba24670d35f399a2a4c664`).
  The subsequent production change only replaces the Windows scrim brush;
  consent/transport behavior is unchanged. Do not describe every row below as
  an exact-final-artifact run.

### Executed evidence

| Case | Evidence / result |
| --- | --- |
| US default-on | Mac DMG and Windows installer/portable: one welcome, no prompt; actual D1 launch and current version recorded |
| EU allow | Same packages: actual Share analytics button invoked; D1 launch recorded after permission |
| UK / unknown deny | Same packages: prompt and Not now exercised; queried final IDs absent from installations; no product events |
| Windows base matrix | Run `20260908000000000000000000000017`, 8/8 cases passed |
| Real two-minute expiry | Mac DMG and Windows installer/portable: allow at 125s, observe through 140s; launch may proceed, expired browser link does not; no second welcome |
| Offline first launch/recovery | Mac prior final-DMG candidate and Windows installed/portable run `20260908000000000000000000000015`: real HTTP proxy failure, backoff respected, online reopen delivers without reopening welcome |
| Closed original download tab | Real built preview site, fresh packaged Windows claim: source `qa-preview-matrix` survives tab closure, reaches installations.source |
| Browser denial / GPC | Same live preview browser contract: zero consume requests for each |
| Claim replay | Same identity retry HTTP 200; different browser identity HTTP 404 |
| Browser transient failure / closed thank-you tab / different profile | Local built-browser regression with intercepted API: passed, no guessed source or recreated tab |
| Final-ten-second consent and expiry | Browser controlled-clock regression: both passed, no polling after grace |
| Consent presentation | Real Windows installed screenshot: centered in-app panel, four scrim bands, all buttons dimmed behind it, explicit black backdrop pixel `[3,3,3]` |
| Windows automatic focus | **Under investigation.** Actual foreground PID remained Brave after the app's initial request, but run 20's later QA-process native activation succeeded. This does not establish OS refusal of the in-app call. Tk focus is not OS foreground proof |

Live D1 verification for final Windows profiles found exactly the four allowed
installations, each with one `app_opened` event, platform windows and first/current
version 0.1.8. The four refused profiles were absent. Mac US and EU IDs likewise
had actual first_launched_at values; queried UK/unknown IDs were absent.

### Regressions and evidence limits

- `request_window_foreground` targets the Windows native wrapper once and
  respects refusal. No input-queue attachment, simulated input, persistent
  topmost, or repeated activation is used in production.
- The visual QA runner records automatic foreground separately. When absent,
  it explicitly raises only its owned test window for capture, removes that
  test-only topmost state, and labels the screenshot accordingly.
- Windows `SS_BLACKRECT` inherited a gray system brush. The focused backdrop
  owner now registers an explicit black-brush child class. A pixel assertion
  catches this regression; geometry-only success is insufficient.
- Preview fresh-install tests twice exhausted the real 20/IP/day quota. Only
  the exact QA `new_ip` counter was reset; production was untouched. Earlier
  quota-refused runs remain failures, not successful launch evidence.
- A launch may already have a validated credential receipt and D1 row before
  the legacy local first_launch_confirmed flag is set by its separate caller.
  Local flags alone are not delivery proof; D1 and the credential receipt are
  checked independently. Server idempotency prevents duplicate rows.
- Whole-browser closure and browser-unavailable behavior retain source/isolated
  browser coverage, not a new full packaged/default-browser run on both OSes.
  Attempting `BROWSER=/usr/bin/false` on Mac did not override its default adapter
  and is **not** accepted as an unavailable-browser test.
- No claim of macOS Intel execution, signed/notarized release artifacts,
  actual HeyCatch delivery, or universal OS focus behavior is made.

Local receipts: `build/windows-genesis/final-preview-matrix.json`,
`extended-preview-matrix.json`, `final-browser-contract.json`,
`consent-black-scrim.png`, `build/preview-browser-regression-final.json`, and
`build/preview-journeys/focus-dmg-*`. Windows raw runs remain under E:\VODForgeQA.
FAST passed at `reports/20260908T081031941051Z-e2f28404-fast/fast-gate.json`:
907 repository tests passed, 25 display-dependent tests skipped in that run;
native rendering was verified separately. Existing nonblocking complexity debt
remains visible. This does not turn older NORMAL/DEEP runs into current E2E proof.

## Genesis Windows follow-up — 2026-09-08 UTC

Windows 10 Pro x64, console session 1 on desktop-genesis. Source archive
`d3b631269d4fd9a878531dd93d4b21a53f0398aa`; private executable SHA-256
`fa07680f492ac12afbfeb4a16b05aff0eef9b1e569854774df71c33c8686c719`.
Builds, installed candidate and receipts are retained under `E:\VODForgeQA`.
The build has telemetry disabled and is not a signed public release.

- Native permission/startup tests: 24 passed on Windows; the same 24 passed on
  macOS. Region transport and browser opening are simulated in these tests.
- Real installed executable: visible in 0.840s / 0.833s on fresh launch/reopen,
  both normal exits zero. Its isolated profile created no credential/outbox.
  The actual screenshot is `build/windows-genesis/installed-app.png`.
- Real libVLC packaged journeys passed from the build directory, installed EXE,
  and freshly extracted portable ZIP. They cover play/pause, seek, volume,
  resize, MP4/MP3 switching and close/reopen. These are backend probes, not
  complete Forge/download UI journeys or long-duration sync certification.
- Installer SHA-256:
  `e4dc41f5045312c17ab56168270a900834ef1f1fdb75032428acd622f828d13f`.
  Portable ZIP SHA-256:
  `3c3885d8841a05732a9c82527c0af1d50e19d45d7baa3a13b48d79fd4edf462e`.
- Actual OS default-browser loopback page loaded in 0.375s. It was not the
  foreground window when checked. This is one observed outcome, not a promise
  that Windows will never focus a browser. A background test tab may remain;
  the probe intentionally does not manipulate unrelated browser tabs.
- Built site at `vodforge-site` commit `8f82d50` passed all ten browser scenarios
  in isolated Windows Brave. Real 135.128s expiry run: 13 polls, zero consumes,
  no polling after expiry. All API/external HTTPS calls were intercepted.
- Fresh Brave reports GPC=true. It correctly suppressed the initial no-GPC
  fixture. The shared policy matrix now explicitly sets simulated privacy
  signals per scenario rather than inheriting browser defaults. Production
  behavior was not changed. This disproves any expectation that all US visits
  should link regardless of browser privacy signals.
- A stale pre-fix static site build was detected and rebuilt before acceptance.
- FAST passed after correcting test formatting and documenting the fixed-HTTPS
  cancellation URL at the Bandit callsite. NORMAL ran 29 pass / 2 fail / 1 skip;
  DEEP ran 30 pass / 2 fail / 1 skip with 19/19 pipeline scenarios passing.
  DEEP's only failed commands were known complexity debt; its other failure is
  change-surface debt. Full packaged journey remains skipped, not green.

Evidence is in `build/windows-genesis/` and
`reports/20260908T042401499849Z-d3b63126-deep/`. These runs include uncommitted
runner/comment/format changes and are not exact clean release checkpoints.
Completed disposable scheduled tasks were removed; Kryden was untouched.
Initial packaging used PyInstaller's default C: cache before the runner was
corrected to keep future cache/runtime diagnostics on E: as well.

**Still unproven:** one combined packaged first-launch → real browser → deployed
Worker/D1/HeyCatch journey. Cloudflare D1 environments use separate database
bindings, not row labels. Current site config has only production DB binding;
remote database inventory failed with Cloudflare authentication error 10000.
An isolated test Worker/database plus build-bound test transport is the next
step. Never enable production collection to bypass this gap. The current
macOS-specific full-journey recorder does not certify these Windows probes.

## Earlier controlled local verification

Controlled local verification, not a packaged macOS/Windows release signoff.
Desktop base: `7f5d48e`; website base: `f6b73db`, plus the boundary fix in this checkpoint.

## Executed matrix

| Scenario | Evidence | Result |
|---|---|---|
| Default-on region | Real Tk event loop, simulated 50ms region request | One browser request at 0.062s; no prompt |
| Opt-in region | Same | One browser request at 0.063s; prompt at 0.104s; no claim before Allow |
| Unknown region twice | Same | Two requests; browser at 0.118s, prompt at 0.207s |
| Stalled region lookup | Same, response delayed 3s | Browser at 2.507s, prompt at 2.584s; late response cannot enable analytics |
| Retry resolves default-on | Same | Two requests; browser at 0.114s; no prompt |
| Late app Allow | Tk owner integration | Same ticket authorized, browser-opening count remains one |
| Browser consent Allow / denied / GPC | Real isolated browser, API interception | One consume after Allow; zero for denied/GPC |
| Original download tab closed | Real browser, same profile | Saved source retained |
| Different browser profile | Separate isolated browser context | No original source guessed; new anonymous browser identity only |
| Thank-you tab closed | Real browser | No consume; no tab recreated |
| Whole browser closed | Separate headless installed Chrome process | Process disconnected; user's browser untouched. Does not prove OS routing or restart behavior |
| Transient claim service failure | Real browser, first consume returns 503 | Two attempts, successful second response |
| Expired claim | Real browser | No consume |
| Two minutes, no permission | Real elapsed time before boundary fix | At 155s, requests observed at 0,10,...110s only; no identity created |
| Consent in last ten seconds | Real browser with controlled clock | Reproduced failure, corrected; 13 polls including final boundary check, one consume |
| Two-minute expiry after fix | Same controlled clock | 13 polls, zero consumes; no additional requests through another minute |
| Unknown/refused app telemetry | Real Python HTTP against loopback Worker/D1 | Suppressed before granting; legitimate enrollment/update/events succeed after grant |
| Private build, refusal persistence, request timeout, no repeated welcome | Repository regression suite | Passed |

The final boundary check may take up to its three-second request timeout to
finish. A long-suspended tab does not resume checking beyond that grace period.
Browser polling is not a guarantee of attribution: closing the page, separate
profiles, browser denial/GPC, connectivity loss, and late consent can leave an
installation unlinked. App permission and allowed direct telemetry are separate.

## Regression coverage and receipts

- `tests/test_analytics_native_journey.py`: five opt-in real Tk timing scenarios.
- `quality_harness/analytics_browser_journey.js`: ten reusable browser scenarios,
  fully intercepted API and external HTTPS traffic, including deadline regression.
- Updated existing `unit_static.telemetry_local_contract` to require explicit
  canonical analytics permission, not a historical browser-claim receipt.
- Local contract receipt:
  `reports/20260907T222205343964Z-7f5d48ec-normal/results.json` (source had WIP
  harness changes; not an exact clean release-candidate receipt).
- 885 repository/harness tests passed; 22 native tests skipped in that run.
  Five newly added native journeys passed separately. Existing 17 unchanged
  native UI cases were not repeated in this pass. Ruff and canonical mypy pass.
- Website: 77 tests pass; Astro diagnostics clean.

## Remaining platform proof

Not executed: exact packaged application startup through the actual OS default
browser handler; minimized/background focus behavior; actual Safari/Firefox
versus Chrome download/default mismatch; Windows installer and portable journeys;
one combined real app-to-browser-to-production-provider journey. Browser profile
isolation simulates storage separation, not different browser engines. Native
tests intercept the opening request and region service; they do not measure
browser startup/render time. No production D1/HeyCatch test events, deployment,
database migration, or app replacement was performed.
