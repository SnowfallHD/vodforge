# Practical workflow discovery and click counts

This bounded harness preserves existing gates and distinguishes conditional source
models, witnessed headless paths and historical native observations. No thresholds
change. Product base: `974e6aff28fa2c421344ddf0d7b128dabf15b0bd`; released
`c6684b2` remains the product negative control. Later integration source needs its
own evidence; these observations cannot be relabeled as successor acceptance.

## Run and inspect

```sh
PYTHONPATH=engineering-quality /Users/coop/Dev/vodforge/.venv/bin/python -m quality_harness.workflow_coverage --summary
PYTHONPATH=engineering-quality /Users/coop/Dev/vodforge/.venv/bin/python -m quality_harness.workflow_coverage > /tmp/vodforge-workflow-matrix.json
VODFORGE_WORKFLOW_EVIDENCE=/tmp/vodforge-workflow-observation.json QT_QPA_PLATFORM=offscreen /Users/coop/Dev/vodforge/.venv/bin/python -m pytest tests/test_workflow_coverage.py -q
PYTHONPATH=engineering-quality /Users/coop/Dev/vodforge/.venv/bin/python -m quality_harness.workflow_coverage --evidence /tmp/vodforge-workflow-observation.json --summary
```

Optional `--native-observations <owner-manifest.json>` imports hash-verified historical
observations separately. The importer requires matching nonempty source revision,
process/window ownership, visible window, normal exit, no survivors and artifact
hashes. It never converts predecessor observations into current validated edges.
Tests use temporary profiles and offscreen Qt; this harness does not launch native
windows, install software or send telemetry. Integration owns native input.

## Two catalogs and discovery

The semantic location catalog includes root screens, Python route constants,
instantiated menus/dialogs/windows and selected run states. Source-defined popup
inheritance is resolved: this discovered two CaptionTracks popup consumers that
name-suffix heuristics missed. Reusable component definitions are excluded as locations
with reasons, while their bindings remain inspectable.

The semantic feature catalog consolidates bridge commands and local UI operations,
retaining all parameterized source entries. Same-file signal adapters and their
consumer consolidate into one operation. Named operations have aliases: Find media
includes missing-media review, item menu and file menu openers. Input declarations
without callbacks remain editable/selectable controls; focus costs one click, while
typing, dragging and keyboard work are explicitly outside the click metric. Read-only
fields remain distinct viewing controls. Handler operations and editing a field can
be different semantic features; these are discovered families, not a certified count
of all practical product actions.

Every source site remains classified: user input, forwarding, signal declaration,
lifecycle, renderer adapter, alternative input or unreviewed state listener. No
unreviewed listener is silently treated as a user action or not applicable. Raw
candidate coverage remains separate for auditing. Adding either catalog expands its
literal crossproduct; absent connections retain null validated counts.

On this product base: **37 QML files, 1,332 lexical object candidates, 478 handlers,
33 signal declarations and 27 input declarations**. Semantic discovery reports
**100 locations × 259 feature/control families = 25,900 pairs**. Conditional models
cover **4,655 pairs**, including **110 above three clicks**; **21,229 are unresolved**
and **16 have directly source-guarded selected-run not-applicable contracts**.
The latter never substitute another selected owner. Only **one pair** has current
headless validated reachability. Three historical Windows journeys cover **two
semantic pairs**; current native validated edges remain **zero**.

Raw candidates are separately **130 locations × 467 candidates = 60,710 pairs**.
Classification denominators: 282 user-input handlers, 53 forwarding sites, 33 signal
declarations, 27 input declarations, 118 unreviewed state listeners, 11 lifecycle
sites, 11 alternative-input sites and 3 renderer adapters. Lexical scanning is not
a QML compiler or runtime proof. Dynamic states and repeated delegates remain open.

The actual supplied headless scene reads **1,293 raw Qt candidate instances**:
**299 user-control instances**, consolidated into **263 runtime families**, with
**994 auditable infrastructure/adapter exclusions**. Of user-control instances,
**169 lack a literal source-name match**. Exclusions distinguish timers, keyboard
attachments, dialog configuration, overlays, explicitly noninteractive instances
and unnamed left-button wrappers. Independent named or right-click MouseAreas
remain controls. These counts describe this one scene, including hidden instances,
not every app window or a count of missing product features.

## Click semantics and findings

Navigation, menu opening, selection, action and safety confirmation are separate
steps. A directly visible action is one click; menu plus action is two. An already
open popup does not invent selection/navigation steps. Confirmations are retained.
Source models take the least cost among known conditional entry paths. Validated
paths take the shortest among supplied witnessed edges; neither proves global
native optimality. Null is unknown, never zero or unreachable.

Representative conditional findings:

| Starting context | Action | Clicks | Meaning |
|---|---|---:|---|
| selected failed Issue | Retry | 1 | correct selected target required |
| selected terminal Forge run | menu then Dismiss | 2 | selection already made |
| Library home | Forge, select queued run, menu, Remove | 4 | UX review, active owner must remain intact |
| Forge home | Library, select item, menu, Find media | 4 | alternative to longer Issues route |
| Library Issues | select missing item, Find media | 2 | source conditional |
| any of three open media/item menus | Find media | 1 | popup already visible |
| selected saved item | menu, Trash review, confirmation | 3 | necessary safety retained; successful delete unverified |
| Forge idle | output chooser | 1 | historical native initial-directory/Cancel proof |
| Forge idle | Settings then Browse | 2 | historical native initial-directory/Cancel proof |

The older five-click Forge→Issues Find model is retained in earlier evidence as a
provisional model. Alias discovery now finds the four-click item-menu route; no
native shortest-route measurement is implied. Unresolved async popup entry chains
are not invented. No native unreachable claim is established. Windows Dropbox
permission denial, OS shell success, destructive persistence, floating-player drag,
all media/selection/player states and visual layout still need independent evidence.
A graph cannot certify cropping, chrome, glyph quality or ultrawide polish.

## JSON and evidence contract

Schema 2 separates `inventory`, `candidate_coverage`, `semantic_coverage` and
`historical_native_receipts`. Semantic `catalogs` exposes entries, source reasons,
classifications and assumptions. `rows` contains every location×feature pair with
modeled click count/path/status, separately validated count/path/status, preconditions
and optional historical observations. `exhaustive_app_coverage=false`: only the
registered catalog crossproduct is exhaustive.

Source records bind file, line, owner, expression, calls, ancestor contexts, binding
SHA-256 and whole-file SHA-256. Runtime records retain instance name/type/signals,
visibility/enabled state, source matches, family and exclusion reasons. No signal is
invoked during inventory. Runtime matching is evidence to review, not proof of a
source connection or effective visibility at a particular item state.

Witnessed edges require `from`, `to`, `site`, matching `binding_sha256` and
`file_sha256`, tier `headless_ui`/`native_ui`, independently reviewable `receipt`,
`visible=true`, `enabled=true`, and ordered step tokens (`navigation`, `menu`,
`selection`, `action`, `confirmation`). Missing/changed/hidden/disabled evidence is
rejected. An unrelated rejected edge cannot erase a valid path. The historical
importer verifies artifacts but still preserves each original observation's limits.
Legacy `handler_candidates` accounting includes input declarations enrolled for
witnessing; inventory keeps the 478-handler and 27-input denominators separate.

## State consistency and negative controls

`reconcile_views` compares independent projections with authoritative run identity,
state, origin and retry lineage, expected membership and duplicate identity. Fault
controls cover stale state, wrong target/predecessor, omitted views and duplicates.
These synthetic faults validate the checker; they are not product acceptance.

A separate production-owner journey admits a terminal Forge retry while another
owner is active, selects its Issues inspector, reads Run Deck and durable queue,
removes the queued retry, then checks all three again. It requires new attempt
identity, lineage, Queued/removal parity and preserved independent active status.
Issues lacks public full-lineage projection, so that cross-screen claim stays open.

Existing component inventory mainly scanned legacy Python constructors; interaction
coverage left usability unenrolled. Existing retry tests checked admission or single
views, missing absent controls and cross-view membership. New source-binding and
production-owner tests **both fail released c6684b2** (missing Dismiss; retry absent
from Issues) and pass this base. Useful existing checks are preserved.

Additional classifier negative controls fail the preserved initial draft for valid
path survival, nonempty native revision, nested Issues navigation and independent
right-click controls. Discovery tests also cover inherited popups, signal-consumer
consolidation and fields without callbacks. Original failure receipts are retained;
no receipt is rewritten into acceptance. The focused suite passes **35 tests**;
the preserved draft fails **six representative cases** (including three invalid
revision values). Ruff, formatting and diff checks pass. Evidence is retained locally
in `build/workflow-evidence/semantic-focused.txt`, `prior-c6684b2.txt`,
`adopted-draft-negative-current.txt`, `semantic-summary.json`,
`semantic-report.json.gz` and `semantic-ux-review.json`.

## Draft provenance and remaining work

Before this follow-up adopted the semantic draft, unexplained uncommitted module/test
changes appeared in the dedicated worktree. Parent and integration denied assigning
another writer. Historical authorship remains unknown; absence of another OS writer
was not proved. Parent explicitly authorized sole ownership/adoption after preserving
the original three files, patch and hashes outside the worktree at
`/tmp/vodforge-workflow-draft-20261001/` (`provenance.json`). Subsequent edits were
reviewed, corrected and guarded by expected file hashes. This provenance is not
silently attributed to a known author.

Complete source/runtime state enrollment, review 118 listeners and 53 forwarding
sites, resolve 169 unmatched runtime user controls, and collect a few exact-revision
native outcome journeys through integration. Current state catalogs cover selected
run attempts, not every saved-media/provider/player state. Unreachable declarations
require an explicit reviewed applicability contract and actual evidence. This is a
bounded extensible harness improvement, not exhaustive UI/release acceptance.
No product changes, full rebuild/matrix, publication, normal app replacement or
threshold weakening are part of this work.
