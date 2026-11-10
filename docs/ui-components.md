# Interface components and behavior

VODForge is a powerful, approachable media application. Restraint is a design requirement:
content, typography and spacing establish hierarchy; controls appear where they are useful.
Use one clear primary action for the current task. Secondary actions are quiet. Item
management belongs in a contextual overflow menu, and editing reveals Save and Cancel
only while an edit is active. A technical capability is not a reason to add another
permanent control to browsing.

Judge the entire view at rest: the content and next useful action must be apparent
before the controls. Reveal secondary item actions on hover or keyboard focus, retain
a clear touch/click route through details, and show editing controls only during editing.
Use plain action labels and a single understandable Back control. Do not add counters,
decorative arrows or duplicate navigation beside that Back control. Source and output facts remain
available in item details without occupying the browsing toolbar.

This is the shared implementation catalog. Durable state ownership remains in
[architecture.md](architecture.md); validation and release evidence belong in
[the engineering guide](../engineering-quality/README.md). The active acceptance matrix
must distinguish implementation from native and packaged verification. This catalog does
not certify that every historical surface has finished migration.

## Current design standard for every new UI feature

This section is the normative design contract for the current Qt Quick application.
Use it before laying out a new view or choosing a control. Later explicit user
instructions override this standard; update the relevant rule when they do.
Notes from the earlier Tk interface are kept in history (linked at the end); their
examples, audit counts and screenshots do not define Qt controls.
A reference image illustrates composition; it does not excuse a wrong control role.

### Design a task before a collection of controls

Every view must make three things clear: where the user is, what content or object
is in scope, and the next useful action. Establish hierarchy in this order:
location/navigation, content title and identity, current status, primary action,
editable choices, supporting details. Keep technical details subordinate to the
user's task. Group related content with headings, spacing and a quiet surface or
hairline; do not put every label in its own card.

Choose one primary action per task region. Secondary actions use ordinary shared
buttons; occasional management actions use the captured item's overflow menu.
Consent and preferences are choices, not primary actions. A panel may contain
multiple actions when each has a distinct purpose, but their prominence must make
that purpose apparent. Use concrete labels such as Download, Open this folder,
Save note and Copy source URL. Never expose internal implementation terminology
as navigation or unexplained user-facing status.

### Control selection: meaning determines the component

| User intent | Required control and appearance | Avoid |
| --- | --- | --- |
| Perform an action | `StoneButton`, verb label; primary emphasis only for the next useful action | A checkbox or checkmark inside a raised action button |
| Navigate to a view or choose an inspector tab | Shared button/navigation treatment; selected state identifies the current destination | A second navigation row when the first fits; pretending navigation is consent |
| Independently enable an option or give consent | `StoneCheckBox`: square checked/unchecked indicator and plain label, **no button face**; native CheckBox semantics | Checkable StoneButton, checkbox over a button, click-to-cycle values |
| Select one of a few mutually exclusive values | Existing selected-button group when it fits; explicit current selection. A new radio presentation must use native radio semantics with plain indicators/labels | Several independent checkboxes for one choice; inventing a private segmented renderer |
| Choose from a longer or variable list | Shared dropdown trigger plus `AnchoredPopup`; show the current value and disclosure glyph, then actual choices | A button that silently changes value on each click |
| Expand choices or a configuration section in place | `InlineSelector` or existing disclosure owner; options directly under the trigger, expanded state visible | Detached popup for a persistent inline section; Custom controls far below unrelated fields |
| Turn an immediate setting on/off | Existing checkbox unless an explicitly approved switch is needed; a new switch must use native switch semantics and a named shared adapter | A new switch style per screen; ambiguous selected action button |
| Enter or edit text, numbers or a path | Native TextField/TextArea/TextInput with the shared `StoneField` material; persistent label, separate hint, suitable keyboard/validation | Hint as stored data; buttons masquerading as editable fields |
| Choose a continuous quantity | Existing slider/track owner with named endpoints or units and current value | Dropdown for an inherently continuous value; decorative thumb with no keyboard route |
| Report work | `RunProgress` and the existing activity/status projection; determinate progress only when known | Spinner for completed artwork; invented percentages; color-only success/failure |
| Browse objects | Existing artwork/group/run card or native list delegate; stable identity, title and useful status | A menu of label-only buttons when identity/status/artwork matter |
| Show facts or prose | Shared source/output facts or text document; selectable/copyable full values | Raised buttons for passive labels; padded spaces as columns |
| Offer contextual actions | Shared anchored popup, compact content-fitting rows, captured owner | A large empty menu; mutable selection retargeting an already open menu |
| Request focused input or a decision | `StonePopup` modal with clear title, bounded body and protected action footer | Page-sized empty dialog; losing Save/Cancel below a scroll body |
| Explain an icon briefly | Tooltip and accessible name; essential instructions stay visible | Tooltip as the only label for consent, errors or required configuration |

Selection, expansion, consent and execution are different states. Do not reuse a
control merely because its shape is convenient. If the required semantic family
has no shared adapter yet, add the smallest native adapter to this catalog and
qualify it before adding consumers; do not duplicate rendering or state ownership.
This table describes required behavior, not a claim that every possible family is
already implemented.

### Current shared owners

Paths in this table are under `yt_downloader/qt_quick/` unless otherwise shown.

| Responsibility | Existing owner | Consumer supplies |
| --- | --- | --- |
| Palette and foreground meaning | `../ui_theme.py` | Semantic role, never a local palette copy |
| Button sizes/type/padding | `../ui_button_contract.py`, `../ui_styles.py`, `main.py` context `buttonMetrics` | Named variant and content width |
| Action/navigation material and activation | `StoneButton.qml` | Label, icon, selected state and scoped action |
| Boolean consent/preference | `StoneCheckBox.qml` | Plain label, checked/enabled state and scoped toggle |
| Recessed field/panel paint | `StoneField.qml`, `main.py:Materials`, `../ui_chrome.py` | Geometry; native editing stays in its existing control |
| Floating surface elevation and trigger intent | `StonePopup.qml`, `../ui_chrome.py` | Content, modality, dismissal policy and trigger |
| Anchor/viewport tracking | `AnchoredPopup.qml` | Trigger and enclosing scrolling viewport |
| Persistent inline choices | `InlineSelector.qml`, `ManualMp4Settings.qml` | Options/current value; reuse Custom controls |
| Symbols | `SceneIcon.qml` and approved high-resolution assets | Semantic name/tone and logical bounds |
| Artwork | `ArtworkImage.qml`, `artwork.py` | Owner identity, source, fit/crop policy and explicit size |
| Run card/status/progress | `RunDeckCard.qml`, `RunStatusTone.qml`, `RunProgress.qml`, `ActivityLines.qml` | Existing run projection; preserve delegate identity during progress |
| Catalogs, files and inspector | `LibraryScene.qml`, `LibraryFolders.qml`, `LibraryFolderInspector.qml`, `WatchScene.qml` | Scoped projection and retained navigation/selection |
| Player transport | `PlayerScene.qml`, `PlayerOverlay.qml`, `PlayerTrack.qml` | Existing playback owner and return origin |
| Durable state and execution | `main.py` bridge and the existing runtime/archive owners | Captured current owner; UI must not invent a second source of truth |

Use the shared component, not a copy of its appearance. Keep mutable selection,
callbacks and drafts instance-owned even when presentation is shared. Native file
pickers remain platform-owned.

### Composition, spacing and responsive geometry

- Use an 8 px rhythm for related content: 8 within a control group, 16 between
  related groups, 24 between task sections. Existing compact menu rows may use
  2–4 px gaps. These are logical pixels, not physical bitmap dimensions. Preserve
  an established scene's shared metrics rather than accumulating near-identical
  local sizes. A new recurring metric belongs in the existing shared owner.
- Default/compact/inline action heights, fonts and horizontal padding come from
  `buttonMetrics`. Do not shrink type or touch targets to conceal a layout problem.
  Use the inline variant for the shared compact Back and icon actions.
- Use neutral text for titles and ordinary content, muted text for secondary
  facts, and semantic action/status roles sparingly. Larger or heavier titles,
  proximity and whitespace establish hierarchy before color does. Technical text
  uses the existing monospace family; UI labels use the shared UI font.
- Give peer panes equal prominence when their roles are equal. Forge activity and
  output meet at the middle with 16 px on each side of a fixed 1 px hairline. A
  divider is not draggable unless an actual resize affordance is approved.
- Reserve sidebar, inspector, artwork and list geometry through navigation and
  asynchronous work. Replace the contents of the current region without briefly
  growing neighboring columns, rebuilding every card or exposing transient empty
  states. Navigation is not an excuse for a whole-page refresh animation.
- At narrower widths, first flex search/content and truncate optional labels;
  keep top navigation beside the brand while it fits. Collapse a secondary pane
  deliberately with a clear details route when it cannot fit. Never overlap
  controls or clip required actions. Validate the app's actual minimum size.
- Popups fit their visible contents up to the window limit. Scroll only the body
  when needed; keep primary/Cancel actions reachable. Hidden fields release their
  height. Do not use a stretch spacer to turn a short form into a tall empty one.
- Catalogs and prose scroll vertically. Technical activity wraps long tokens and
  fixes content width to viewport width; hiding a horizontal scrollbar alone does
  not prevent sideways scrolling. Horizontal scrolling is intentional only for
  content rails, where vertical wheel intent still reaches the surrounding page.

### Material, icons, artwork and text

Use the continuous smooth matte substrate and one shared lighting convention.
Actions rest softly raised; hover/pressed/selected use shared concavity. Fields
and preview wells are recessed; passive labels have no control face. Checkbox and
radio indicators retain their own plain choice shape. Keyboard focus stays
visible through the shared focus treatment; never invent a screen-local bright
border, underline or hover glow.

Floating surfaces use `StonePopup`'s shared diffuse outer shadow. Embedded fields
keep their inset material. Elevation must extend beyond the face without changing
its hit area or clipping against the surrounding content. Never add an individual
menu shadow or wrap the popup in another visual system.

The analytics consent surface retains four passive privacy summaries from
`ANALYTICS_BENEFITS`: violet vector emblems above short, single-line labels.
Use four columns when the available content width permits and two otherwise.
These summaries are informational, not buttons or checkboxes. Fit the surface to
its content and keep Privacy details and both consent actions visible.
Consent copy names usage events and system diagnostics; do not call the records
fully anonymous or claim they contain no personal information. Automatic source
links, path contents and credentials remain excluded. Support uses independent,
unchecked plain checkboxes for diagnostics, YouTube source link and output folder.
The folder checkbox requires diagnostics; disabling it suppresses that attachment
without silently enabling diagnostics. The review and submitted attachment use
one projection so only selected evidence appears in both.


`StonePopup` distinguishes an explicit trigger close from Qt's automatic outside
press dismissal. Only automatic dismissal over the trigger consumes that same
press's subsequent click. An explicit close must leave the next deliberate
activation available, even while Qt still reports the pointer button held. The
existing six-menu click journeys missed this held-press ordering; retain the
separate held-press regression alongside those representative shared consumers.
Bind the press to actual window/item bounds: hover can remain stale beneath a
modal overlay. Clear the consumption flag after that release's click dispatch,
including when the overlay swallowed the click. Retire the transient input
observer with its Bridge; never log pointer positions or send them to telemetry.

Use vector SceneIcon glyphs or approved assets with sufficient backing density.
Do not use emoji for interface symbols. Match stroke weight, tone and size across
navigation and compose controls; preserve brand artwork. Copy uses two overlapping
squares, a source link uses the chain emblem, overflow uses the shared dots. Every
icon-only action has an accessible name and tooltip where useful.
Directional emblems must form a coherent silhouette: attach each arrowhead to
its arc at the correct tangent, preserve mirrored directions, and keep numerals
upright and legible. Inspect both the actual control size and an enlarged render;
separate floating corners do not satisfy the icon contract.

Artwork has explicit layout bounds before loading. Preserve actual media colors
and the approved fit/crop rules. The current-folder overview uses a large unframed
folder emblem, centered with its label below. Other intentionally empty preview wells retain their centered emblem;
metadata shows a file emblem inside its concave preview container. A delayed image
cannot become a permanent busy indicator after the run has finished. Loading,
unavailable and intentionally empty artwork are different states.

Text must fit its role. Breadcrumbs stay on one line, emphasize the current folder,
truncate long components and expose hidden ancestors through the shared popup.
Compact Back sits below the trail; Open this folder belongs to the folder inspector.
A path is navigation, not a stack of wrapping buttons. Long card names elide; prose
and facts wrap in a bounded document. Copy/accessibility retain full values.
Truncation for display must never alter saved paths or source URLs. File-system
naming/length budgets belong to the existing path planner, not the UI renderer.

### Interaction, accessibility and state contract

| State or interaction | Required outcome |
| --- | --- |
| Resting/hover/press | Stable bounds; feedback on the control, no page flash |
| Keyboard focus | Visible shared focus treatment, sensible Tab order, no focus theft from an active editor |
| Selected/checked/expanded | State is visually clear and exposed through the appropriate native accessible semantics |
| Disabled | Native disabled semantics and no active callback; explain unavailable required choices nearby |
| Popup trigger | First activation opens, same trigger again closes, with no close/reopen flash; use `toggleFrom(trigger)` |
| Popup dismissal | Escape/outside click according to policy; another deliberate trigger activation can reopen; restore a valid prior focus |
| Nested popup/scroll | Close retired menus; anchored menus follow their trigger and close when it leaves the viewport |
| Inline disclosure | Options appear immediately beneath trigger and stay expanded until that trigger collapses them or their owner retires |
| Pointer cancellation | Release outside or retired/disabled owner cannot execute the captured action |
| Progress update | Update existing delegates/status in place; keep an admitted menu open and its target stable |
| Async completion | Stale owner callbacks cannot overwrite the current view, edit or selection |
| Edit failure | Retain the user's draft and actionable error; only successful durable save reports success |
| Consent | Unchecked by default, separately labeled, explicit opt-in; unavailable data must not appear selectable |

Text controls keep native editing, selection and copy keys. Checkboxes use native
Space/toggle/accessibility behavior, not a Button role with a painted checkmark.
Use words plus symbols for success/warning/failure so color is never the sole cue.
Background editorial prompts wait until text editing and the current task are idle.
Back restores the retained origin, including selected item and scroll, rather than
sending every user to a fixed home tab. Top-level navigation explicitly selects a
main view; contextual Back returns to the preceding view.

### Empty, loading, partial and recovery states

Each region owns its empty state. An empty Playlists section keeps its approved
placeholders even when Videos has content; See All is inactive until that section
has at least one item. Placeholders never impersonate real items. Loading preserves
known content and geometry, defers brief transient messages, and shows truthful
feedback when a wait persists. Verified empty/error results replace stale content.

Run Deck represents all retained runs with their actual state, including stopped,
canceled, failed and skipped. Issues & Recovery represents unresolved problems;
normal downloads do not become issues. A retry stays visible there with its live
state until success. Removed queued items are removed, not mislabeled as stopped.
The header includes a quiet, accessible X link to `https://x.com/VODForge`, beside
Settings. It opens in the system browser without media or installation context;
include its utility width in the shared responsive budget.

My Files uses recognizable filled vector folder icons in its list. The current
folder inspector shows a larger unframed folder emblem with its name below; actual
media artwork and metadata file previews retain their shared inset treatment.
Folder illustration never masquerades as a button or a selected media thumbnail.

My Files browses physical folders/files; All media browses saved media independently
of path. Missing media has an explicit route to its recovery item. Recovery cannot
claim a file exists, a repair succeeded or an export completed without that owner's
verified outcome. Optional diagnostics remain a separate, explicit data choice.

### Required review for a new feature or changed component

Before implementation, identify the task, existing owner/component, primary action,
scoped object, data/consent boundary and intended narrow layout. Add a new shared
adapter only when an existing semantic family cannot express the behavior.

Before calling the result complete:

1. Review the whole view at normal and minimum supported sizes, including long
   names/paths/prose, zero/one/many items and all expanded configuration sections.
   Confirm hierarchy, alignment, separation, legibility and reachable actions.
2. Exercise the relevant control states with actual pointer and keyboard input:
   open/close/reopen, outside/Escape dismissal, selection, disabled state, editing,
   error/retry, scroll and navigation while work updates. Inspect role/name/value
   for new accessible controls; a painted symbol is not accessibility proof.
3. Verify shared changes on representative independent consumers, including a
   known-bad/prior implementation when fixing a bug. Explain why existing coverage
   missed it and strengthen that invariant in the existing harness.
4. Inspect the exact built app for user-facing visual changes. Record source and
   artifact identity, preserve failures, and distinguish source/offscreen checks,
   native packaged observation and untested platforms. Tests alone cannot certify
   that a scene looks good. Stop when the agreed criteria are met.
5. Update this canonical contract when a rule or shared component changes. Keep
   implementation/evidence notes in their appropriate guides; do not add a competing
   design document or silently leave contradictory current guidance.

These constraints give new features a consistent starting point and concrete
acceptance criteria. They do not promise that arbitrary new UI automatically looks
good without reviewing its content, layout and actual rendered states.

## Approved scene references and later instructions

Use the actual approved VODForge mockups for whole-scene comparison:

| View | Approved reference |
| --- | --- |
| Library populated | [Library populated](references/library-populated.png) |
| Library empty | [Library empty](references/library-empty.png) |
| Library item details | [Item details](references/library-item-details.png) |
| Watch populated | [Watch populated](references/watch-populated.png) |
| Watch empty | [Watch empty](references/watch-empty.png) |
| Watch channel | [Channel page](references/watch-channel.png) |
| Player | [Player reference](references/player.png) |

[Reference identities](references/approved-mockups.json) retain supplied
filenames and SHA-256 hashes. These are generated design references, not evidence
that the running application has passed a usability review. Earlier application
screenshots are regression observations, not replacement design specifications.

Preserve the approved Library category cards, sidebar, collections and recent
downloads composition. The mockup explicitly includes the local media search row.
Restraint means coherent hierarchy and contextual actions within this design;
it is not permission to remove approved structure based on a generic preference.

Later explicit user instructions supersede conflicting reference details:
the earlier Library texture omission is superseded by the September 19 matte
material contract below; use one item overflow with vertical dots,
retaining inline edit/copy; show full bounded descriptions and editable tags;
restore complete truthful source/output facts including separate audio/video
bitrates. Player uses a larger 16:9 Fit viewport preserving the entire source,
with letterboxing or pillarboxing as needed, More to Watch vertically at right,
Recently Added horizontally below, and expanded details below the description.
The shallow cropped player and duplicate action rows in earlier mockups do not
override those later instructions. User-created collections belong between
Recently Added and Playlists in Watch.

Compare complete scenes at representative window sizes and data states, including
empty and one-video playlists. Record intended responsive differences, typography,
spacing, content hierarchy and control states alongside functional evidence.
A cropped scene screenshot or a single polished button cannot establish parity.

The header includes a quiet, accessible X link to `https://x.com/VODForge`, beside
Settings. External social links open in the system browser without sending media
or installation context. Keep utility width in the shared responsive budget.
