# Practical workflow discovery and click counts

This harness addition keeps the existing gates and reports source models separately
from independently observed UI paths. It does not change release thresholds.
The reviewed product base is `974e6aff28fa2c421344ddf0d7b128dabf15b0bd`;
released `c6684b2` remains the negative-control baseline.

## Run it

From this checkout, using the project's existing Python environment:

```sh
PYTHONPATH=engineering-quality /Users/coop/Dev/vodforge/.venv/bin/python -m quality_harness.workflow_coverage --summary
PYTHONPATH=engineering-quality /Users/coop/Dev/vodforge/.venv/bin/python -m quality_harness.workflow_coverage > /tmp/vodforge-workflow-matrix.json
QT_QPA_PLATFORM=offscreen /Users/coop/Dev/vodforge/.venv/bin/python -m pytest tests/test_workflow_coverage.py -q
```

To collect the maintained offscreen pointer observation and include it in the report:

```sh
VODFORGE_WORKFLOW_EVIDENCE=/tmp/vodforge-workflow-observation.json QT_QPA_PLATFORM=offscreen /Users/coop/Dev/vodforge/.venv/bin/python -m pytest tests/test_workflow_coverage.py -q -k headless_pointer
PYTHONPATH=engineering-quality /Users/coop/Dev/vodforge/.venv/bin/python -m quality_harness.workflow_coverage --evidence /tmp/vodforge-workflow-observation.json --summary
```

The default full JSON includes every location × feature/candidate pair. `--summary`
is a compact denominator readback. Nothing installs, launches a native window,
changes an ordinary profile, or sends telemetry. Tests use temporary isolated profiles.

## Two catalogs and the discovery denominator

`LOCATION_CATALOG` declares the four main screens and baseline context.
`FEATURE_CATALOG` declares eight important operations, their preconditions and
production call names/aliases. Adding declarations expands the crossproduct.
Source discovery also expands both catalogs automatically: all QML component
contexts, popup/dialog/menu instances, Python constant routes, and all QML handlers.
Undeclared input handlers, forwarding connections and unreviewed events are separate
categories. They remain visible rather than disappearing from the report.

On the fixed base, discovery finds **37 QML files, 1,332 lexical object candidates,
478 handler sites and 33 signal declarations**. The catalogs contain **120 location
candidates × 473 feature/control/event candidates = 56,760 pairs**. Feature categories
are **8 named operations, 284 additional input-handler candidates, 39 forwarding
candidates, and 142 unreviewed event candidates**. These are source sites, not 473
distinct user actions or proven visible controls. Repeated delegates and shared
components need runtime identity/multiplicity review.

The source model supplies conditional paths for **2,936 pairs**, including **69
above three clicks**; **53,824 remain unresolved**. A real offscreen pointer click
on Forge's All N runs control changes the production bridge to Library: **one
validated pair and one observed handler site out of 478**. Native coverage is **zero**.
Native integration retains sole GUI ownership.

## Click semantics and representative output

One visible actionable control costs one click. Menu opening, navigation, selection,
and confirmation are separate steps. A confirmation handler counts as confirmation,
not as a second invented action. A source model enumerates primary entry alternatives
and takes the least cost conditional path. Safety steps are retained. Right-click and
keyboard alternatives remain a separate unverified field.

These examples start on each main screen's home baseline without a selected item:

| Control/operation | Forge | Library | Watch | Activity |
|---|---:|---:|---:|---:|
| Retry a terminal run | 3 | 4 | 4 | 4 |
| Open Find media chooser | 5 | 4 | 5 | 5 |
| Open saved output location | 3 | 2 | 3 | 3 |
| Open Trash review for saved media | 4 | 3 | 4 | 4 |

Opening Find media from Forge is modeled as Library → Folders → Issues → select missing
item → Find media. Starting on Library/Issues reduces that model to selection →
Find media (two clicks). Queue removal from Library is modeled as Forge → select
queued owner → menu → Remove (four). Trash review is selection plus menu plus
review action from Library; **this counts opening review, not successful deletion**.
The destructive confirmation is a separate discovered handler and must be connected
and observed before a total successful-delete journey can be certified.

These are conditional source models, not measured native shortest paths. In particular,
component containment, main navigation declarations and source popup ancestry cannot
prove actual visible bounds, modal dismissal, picker permissions or action eligibility.
Unknown input contexts, dynamic screens and unclassified event sites get null counts.
No action is declared unreachable merely because no native observation exists.
A source-backed menu opener remains an explicit validation assumption in the model.
High-value unresolved examples include Windows cloud-file verification/picker denial,
actual destructive commit paths, generic Main.qml popup entry ownership, and floating
player interactions. No native unreachable claim is established by this run.

## JSON contract

The outer report has `inventory` and `coverage`:

- `inventory.files` binds every scanned file by SHA-256; `inventory.sites` includes
  file/line, source handler expression, calls, owner type, ancestor menus, source
  properties, binding SHA-256 and whole-file SHA-256.
- `coverage.catalogs.locations` has `id`, `kind`, `baseline`.
  `coverage.catalogs.features` has `id`, `kind`, `sites`, `primary_entries`,
  `precondition`, and optional source call declarations.
- `coverage.coverage.goals` contains one row per pair: `from`, `feature`, `to`,
  baseline, precondition, `modeled` count/path/step types/confidence/status,
  `validated_click_count`, witnessed `path`, validated status and alternatives.
- `coverage.matrix_denominator`, `feature_kind_counts`, `status_counts`,
  `modeled_status_counts`, and `coverage.coverage.counts` are separate denominators.
  `exhaustive_catalog_crossproduct=true`; `exhaustive_app_coverage=false`.

An observation file contains `edges` (or an `evidence.edges` wrapper). Each edge has
`from`, `to`, `site`, `binding_sha256`, `file_sha256`, `tier` (`headless_ui` or
`native_ui`), `receipt`, `visible=true`, `enabled=true`, and an ordered `steps` list.
Step tokens are `navigation`, `menu`, `selection`, `action`, `confirmation`.
An action target is `action:<feature-id>`. A location target is its catalog ID.
The receipt is a pointer to independently reviewable evidence, not an automatic
attestation that a claim is true. Changed/missing binding, changed whole file,
source-only claims, missing receipts, hidden/disabled controls and undefined step
types cannot establish validated reachability. Shortest validated paths are shortest
among supplied witnessed edges, not a proof of all possible alternatives.

Currently observed statuses are `reachable`, `ux_review`, or `unverified`. The harness
deliberately does not infer `unreachable` or `not_applicable` from absent observations:
those require an explicit reviewed item-state/applicability contract. That enrollment
is still outstanding. Null counts mean unresolved availability/route, not zero clicks.

## State consistency and failure learning

`reconcile_views` compares independently read projections with canonical run identity,
state, origin and retry lineage, including expected membership and duplicate identity.
It detects stale state, a wrong target, a wrong predecessor, omitted views and duplicate
rows. Synthetic fault tests validate these rules, not the product by themselves.

A production-owner journey separately admits a Forge terminal retry while another
owner is active, selects its Issues inspector, reads Run Deck and the durable queue,
removes the queued retry, then rechecks Issues, Run Deck and durable queue. It requires
new attempt identity, original lineage, Queued parity, removal parity, and preservation
of the independent active owner's status. The Issues inspector does not expose full
lineage in its public projection; full cross-screen lineage attestation remains an
explicit limitation. No hidden mutation supplies lineage to that view.

Existing `component_inventory` primarily scans legacy Python button constructors;
`interaction_coverage` deliberately leaves usability unenrolled. Existing retry tests
checked admission or individual views, but did not automatically discover absent
controls or measure paths from arbitrary contexts. These checks preserve that useful
coverage and add source discovery, literal cost accounting and bounded shared-state
outcome assertions.

The new source-binding and production-owner journey tests both fail on released
`c6684b2`: the Dismiss binding is absent, and a Forge-admitted queued retry is absent
from Issues. Both pass on `974e6af`. Removed bindings also erase modeled reachability;
stale/wrong-target/wrong-lineage mutations produce findings. The focused suite passes
20 tests. The two prior-source failure logs are retained in the local evidence directory
rather than relabeled as acceptance. The initial fixture setup failed on assigning a
read-only status property; the corrected fixture supplies a real owner status event.

## Remaining enrollment and review

Review the 39 forwarding sites against their component signal consumers, then classify
the 142 lifecycle/event candidates. Resolve Main.qml contextual entry ownership and
state-specific availability before expanding successful effect journeys. Derive runtime
item-state catalogs (including missing/denied files, selections, active/queued/terminal
attempts and modal states), then compare scene inventories to source candidates and
review explicit not-applicable/unreachable cases. Add a few real native clicked
journeys through the integration owner, binding exact product revision, profile,
window, selected owner and durable outcome. Do not turn the provisional candidate
catalog into an exhaustive runtime or visual-polish claim. No full rebuild/matrix,
production change, publication, ordinary app replacement or threshold relaxation.
