# Analytics journey evidence — 2026-09-07

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
