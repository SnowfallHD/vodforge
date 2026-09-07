# Analytics journey evidence — 2026-09-07

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
