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

[Reference identities](references/approved-mockups.json) retain original supplied
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

## Choose an existing owner first

| Capability | Canonical implementation | View responsibility |
| --- | --- | --- |
| Palette and fonts | yt_downloader/ui_theme.py | Choose semantic roles |
| Native widget variants | yt_downloader/ui_styles.py and ui_widgets.py | Choose primary, quiet, compact or icon treatment |
| Scene typography and controls | scene_components.py:ScenePainter | Supply content and scoped callbacks |
| Surface and focus geometry | ui_chrome.py | Supply bounds, preserve keyboard focus |
| Canvas pointer gestures | ui_canvas_actions.py:CanvasActions | Expose current render's targets |
| Mouse and trackpad routing | ui_scrolling.py:ScrollBinding | Enroll actual scrolling widget and external targets |
| Scrollbar orientations | ui_widgets.py:SleekScrollbar | Bind xview/yview and matching reports |
| Scoped keys | ui_widgets.py:KeyboardScope | Supply actions for this subtree |
| Protected popup body/footer | ui_widgets.py:ActionDialogSurface | Put Save/Cancel in footer |
| Empty-field hints | ui_widgets.py:PlaceholderEntry | Keep hint separate from stored StringVar |
| Full inline text/editing | ui_editable_text.py:EditableTextSection | Supply owner, text and durable save callback |
| Label/value documents | detail_ui.py:FactsText | Supply original content, never padded spaces |
| Comparison fields | encoding_summary.py | Distinguish source, measured output and target facts |
| Library fact projection | library_scene_facts.py | Present recorded facts and unknowns |
| Durable personal edits | library_annotations.py | Resolve captured owner before save |
| Bounded catalog geometry | scene_paging.py:visible_scene_rows | Continuous logical extent with nearby rows drawn |
| Horizontal content rows | scene_rail.py:SceneRail | Supply items, renderer and current-owner actions |
| Artwork lifetime | archive_artwork.py and archive_presentation.py | Retire stale work and request visible artwork |

Paths without a directory prefix above are within yt_downloader.

Before creating another component, inspect its owner and usages. Extend existing behavior
when semantics match. Never share selection, action targets, popup instances or mutable
closures merely because views look alike. Library and Watch have separate targets despite
sharing pointer and scrolling behavior.

## Controls and hierarchy

Action buttons have one metric contract in ui_button_contract.py, resolved by two
rendering adapters: ProductButton/ttk styles/chrome and ScenePainter.button. ProductButton keeps
native ttk keyboard/rendering behavior and owns per-instance pointer admission:
release outside, disabled state, callback replacement or another button's press
cannot activate an action. Scenes retain CanvasActions gesture ownership. Default
labeled actions use 44-pixel height and 15-pixel type; Compact.TButton uses
40-pixel height and 14-pixel type. Style aliases do not define extra sizes.
Accent.TButton and primary=True select primary emphasis; ordinary/FocusQuiet
actions select secondary emphasis; quiet scene actions suppress the surface.
Navigation and player transport remain separate component roles under audit.

The [constructor inventory](../engineering-quality/acceptance/UI_COMPONENT_INVENTORY.json)
records 93 ProductButton constructor sites and 31 ScenePainter button call sites. These are
static sites, not runtime widget counts or a proof that every branch executes.
The five Library icon-only sites use the same metric owner: inline copy, tag-add
and collection overflow use a 32-pixel square; media-card overflow matches the
44-pixel labeled action beside it. ScenePainter.button accepts variant="inline"
and width=None for a square derived from the selected metric. Views position the
control but cannot override its height or font. The inventory rejects overrides
for icon-only actions as well as labeled actions. The unreachable legacy Watch renderer and its
four private helper methods were removed after checking production and test
references. This count covers ordinary labeled actions only. Specialized transport, poster play,
canvas icon controls are separate families below.

The native parity check constructs the actual isolated application and verifies
Forge Download, Library and Watch empty-view actions, and collection Save. It also
changes the shared specification to 50-pixel height/17-pixel type and confirms
propagation to those same live sites. This is representative source-native
evidence, not all-state, all-platform, packaged or all-component certification.
The five Library icon sites additionally have live size-propagation checks at
32 and 36 pixels and a real wrong-variant negative control. This does not qualify
all specialized icon or player controls.

Follow the [shared-component harness standard](../engineering-quality/HARNESS_GUIDE.md#shared-components-and-consistent-controls)
for inventory, shared-spec propagation, rendered parity, interaction states and
known-bad bypass detection. Views supply labels, content widths and captured
actions; they must not override default action heights or fonts.

Overflow uses vertical dots. Give icon controls a tooltip or understandable accessible
label. Disabled controls must not retain an active callback. Keyboard focus uses a rounded,
high-contrast contour; hover uses the shared concave material face without a brighter border;
press uses the deeper version of that face. Top navigation keeps persistent selected concavity and semantic icon/text roles while
its hover state uses the same indentation without filling the entire control. Feedback belongs
on the control, not a whole-page animation. Artwork may add a contextual play affordance.

Canvas usage:

    self._pointer_actions = CanvasActions(self.canvas, lambda: self._targets)

Targets are (bounds, callback) pairs. Press captures the exact pair; release must still hit
that identical pair. Replacing targets during navigation/repaint retires the gesture.
Clear stale hit targets immediately before scheduling the repaint. Do not dispatch on
mouse-down beside this owner. Library right-click and overflow resolve the same captured
media owner against the current projection before invoking the item action set.

## Surface reuse during a redraw

CanvasSurfaceCache owns both reusable surfaces and the references required by
currently displayed Canvas items. Wrap a synchronous scene replacement in its
frame context before deleting old items:

    with self._depth.frame():
        self.canvas.delete("all")
        # Draw the replacement through the same cache owner.

A frame may reuse an exact previous surface, including a Retina hero larger than
the ordinary cache. Full geometry, role, scale and palette remain part of identity.
The temporary references are released when the frame exits, including on an
exception; unused images still have the same 12-entry/8 MiB LRU limit. Oversized
surfaces never enter that LRU or evict its smaller controls. The bytes property
counts distinct cached, displayed and in-progress frame backings. It is not a
process-RSS measurement and does not resolve the separate native runtime leak.

## Scrolling

The compatibility helper bind_smooth_vertical_wheel in ui_widgets delegates to ui_scrolling.
Use ScrollBinding directly for two-axis surfaces:

    bind_smooth_vertical_wheel(document, scrollbar, mode="pixels")
    ScrollBinding(canvas, header, axis="both", horizontal_targets=(header,))

One binding owns each input widget. Fractional motion accumulates before quantization.
The nearest enrolled ancestor handles nested input; exhausted boundaries forward once.
Construction order cannot select a different owner. Packed trackpad input uses the actual
recipient's Tk decoder. Upward scroll intent releases log tail-follow even on a short log.
Destroying descendants releases callbacks; rebinding replaces only owned callbacks.
Do not use bind_all for scrolling.

PixelScrollTable remains a visible-row adapter. Its redraw callback is enrolled in shared
input; do not redraw recursively from scrollregion reports. Collection Listbox uses row
mode. Visible-row rendering bounds live widgets and artwork; it does not make the
authoritative metadata archive a streamed on-disk database.

## Keyboard and popups

    scope = KeyboardScope(panel, {"<Escape>": close_panel})
    surface = ActionDialogSurface(popup, modal=True)
    surface.bind_keys({"<Return>": save, "<Escape>": popup.destroy},
                      editing=("<Return>", "<Escape>"))

The nearest visible scope to focus wins. One key dispatches one action even if that action
destroys its scope. Text fields retain ordinary editing keys unless explicitly enrolled.
Nested modal close restores the previous valid grab. Teardown removes only owned bindings.

Collection's exact hint is "Type your collection name". It remains visible while empty
and focused, disappears on typing and returns on clearing. It is never stored. Save lives
in the protected footer. Library detail return restores route, group, filter, query, sort,
page and scroll; it does not reset to another group or unconditional root.

## Inline editing, tags and copy

    section.present(owner, full_text, "Source description")
    height = section.height_for_width(available_width)

EditableTextSection displays full text in a bounded-height scrollable document. Copy copies
all content. Edit reveals Save/Cancel; Escape cancels only that edit. Control-Return saves,
as does Command-Return on Mac. Changed owner cancels the old edit. Save receives the captured
owner and returns success; failure preserves entered text.

LibraryAnnotation.description is a nullable local override. None uses provider text; empty
string is an intentional blank. Provider metadata and personal notes remain separate.
Projection exposes vodforge_user_description only for an actual override. Atomic annotation
replacement preserves notes/tags/category and ledger bounds. The older note editor preserves
the description override.

Tags are inline additions/removals. The remove mark and hit region share a center and capture
both owner and tag. Copy returns every tag. One item overflow replaces duplicate Manage and
Add Note controls.

## Facts and wrapping

Source/output use the canonical comparison schema. Video and audio bitrates are separate
in both. Measured output rates never borrow requested targets or provider rates. Missing
measurements remain unknown. Selection metadata, frame rates, codecs, sample rates,
channels, size, dynamic range, targets and validation remain available.

Rows measure the full wrapped label/value before placing the next row. Value continuations
begin at the value column. FactsText applies that hanging indentation to long block values
including paths. Copy preserves full strings, not ellipsized display text. Everyday
description and tags precede technical facts.

Relink review height uses current wrapped Text line metrics, not cached intermediate
estimates. The existing fit_review callback requests count -update -ypixels over only enough logical lines to fill the viewport before
clamping its material surface to available space. All review lines use the base
font or a larger title and none are elided; wrapping can only increase their height.
This bounds synchronous measurement by the viewport, rather than the archive size.
Do not apply that lower-bound argument to a document with smaller or elided text. This refreshes that document's
metrics without pumping application input or idle work. Python/Tk may return a
scalar or one-element tuple, so normalize both. Tk documents the distinction in its
[text count reference](https://www.tcl-lang.org/man/tcl9.0/TkCmd/text.html).
This removes a measured source of repeated sizing; it does not alone qualify
overlay presentation. The staged entry/return owner and its independent frame
checks are described below; retain the earlier blank/partial-frame failures.

## Validation and documentation

Mandatory source classes live in engineering-quality/quality_harness/scene_contract.py:
shared scroll, keyboard, pointer, annotation ownership, geometry and the other scene classes
run in NORMAL and DEEP. Native controls and inline editing are enrolled separately in
quality_harness/native_ui_checks.py. Unit passes do not establish physical trackpad,
drag-release, Windows, rendered-video continuity or installed-package acceptance.

Update the affected component contract here and its canonical architecture/workflow guide.
Regressions should exercise the failure class, not mirror implementation strings. Preserve
failed receipts and identify OS-injected, generated Tk and physical input. Bind evidence to
reviewed source. Telemetry records bounded actions/outcomes, never descriptions, tags,
paths or titles.

README is the product/install/use front door; architecture owns state/module boundaries;
this catalog owns UI contracts; engineering-quality owns testing/release gates. Extend the
canonical guide before spawning another document. Retain historical receipts as history,
but replace stale current-state guidance instead of appending contradictory instructions.

## Player page and transport ownership

The embedded page starts with a Fit video viewport with a 16:9 frame. Its width
also respects available window height so playback remains accessible in short
windows. Related videos sit to the right when space permits and below on narrower
windows; Recent follows underneath. Description, chapters, moments, personal
details, source and output information are normal page sections.

Use one transport surface. A live Mac native overlay owns video controls and
video-body clicks. The Tk transport and body handler remain the fallback for audio
artwork or an unavailable native overlay. Resizing must not remap a hidden fallback
transport. Native delegates queue actions for the existing Tk poll; they never
enter Tcl. Pointer gestures dispatch once on release and reject dragged or retired
gestures. Disclosure telemetry records a bounded section identifier only when the
section enters the visible viewport; it never includes descriptions or paths.

Native geometry is covered by test_player_layout_native.py. Actual generated MP4,
MP3 and original-audio playback, body clicks, fullscreen return, section access and
release are covered by test_archive_actual_playback.py. OS-injected input is not
physical mouse or trackpad certification. These contracts supplement the source
tests and do not certify untested platforms or packaged builds.

## Continuous Watch video catalogs

Watch video results and multi-video playlist pages draw a window of rows around
the visible viewport, using scene_paging.visible_scene_rows. The canvas represents
the complete catalog height; the renderer owns only visible rows plus overscan.
Scrolling uses the shared ScrollBinding and scrollbar, including Page Up/Down.
Library media, channel, playlist and collection catalogs reuse the same row-window
geometry, with their own record/action adapters. Watch group catalogs use the same
bounded geometry; horizontal rows use SceneRail as described below.

Watch caches up to four projections keyed by channel, query and collection mode.
An authoritative record replacement immediately releases the old projection even
while hidden. Collection and title edits invalidate it without requiring media
membership changes. Data replacement preserves the visible row anchor where its
item remains; route/filter changes clear the old geometry. Artwork keeps fixed
card geometry, a bounded decoded cache and bounded requests. An evicted successful
image reloads immediately when needed; the unavailable-source retry delay remains.

The native scale probe separates cold synchronous presentation, warm drawing,
visible decoded-artwork readiness, Python query allocations, current process RSS
and process high-water. Repeated traversal checks observe bounds during a finite
synthetic run; they do not establish universal memory or physical-input guarantees.
Catalog scrolling emits one consented, content-free catalog_scrolled event per
browse visit through user input, rather than an event for each repaint or pixel.
A single saved video uses one featured card; available Collections remain reachable
without repeating that video as a mostly empty Recent row.


Library requests visible thumbnails before overscan artwork, preventing off-screen
preloads from consuming the bounded image budget while a visible channel card is
blank. Its native catalog probe counts actual on-screen artwork against visible
thumbnail/avatar regions, in addition to first/middle/end/back reachability and
data-update anchor checks. Library scroll telemetry reports only the bounded route
once per browse/filter context; user query text stays local.

Mandatory scene contracts check named semantic test identities in the JUnit report
as well as minimum counts and complete success. Removing projection coverage
cannot be hidden by adding unrelated passing cases.


## Continuous catalogs and horizontal rows

Library media/groups and Watch media/groups use visible_scene_rows for bounded drawing
over the full logical content extent. This bounds live canvas objects and decoded artwork,
not the authoritative metadata snapshot. Watch caches up to four query/channel/collection
projections and retires them when records change. Preserve the first visible owner on
record replacement and resize; new search/filter/sort starts at its first result.

SceneRail owns one child canvas and horizontal SleekScrollbar per visible section, with
nearby items drawn on demand. It uses the same two-axis ScrollBinding: horizontal motion
scrolls the row, vertical motion forwards to the outer view. Left/Right and Home/End reach
every item; Enter/Space invokes its primary action; Down selects a media card's Details
action and Up returns to Play. Tab moves between surfaces. Retire action targets before
deferred navigation/data repaint and destroy unused rows on route changes. Child canvas
images retain their own references until repaint/teardown. Collections belongs between
Recently Added and Playlists; See All opens the continuous full catalog.

The native catalog suite exercises decoded artwork, both axes, endpoint reachability,
keyboard actions, resize anchoring and route teardown. Its generated events establish
source-native behavior, not physical input or installed-build acceptance.


## Top-tab reveal

ViewTransition prepares a mild blur of the outgoing view through
platform_services.capture_own_widget before the destination is exposed. Its sibling
cover already has pixels when mapped. After the initial 72 ms interval, bounded
destination drawing can yield between up to three passes before reveal. macOS
uses its native idle-drawing bridge; Windows uses the existing surface adapter
to make one owned-target redraw attempt without pumping input. An unavailable
Windows attempt is recorded as a bounded fallback, not as evidence that the
destination had pixels. Neither path owns view state. The soft drawing budget
cannot preempt a callback; 72 ms is not total completion latency.
The destination never appears sharp and then regresses to a blurred snapshot.
The app releases any embedded player before preparing this cover. It reads only
the application's own native content. One generation owns its timer, overlay,
and image references. Another
top-tab selection replaces that generation; within-tab route changes call
cancel_view_transition. Resize, teardown, unsupported rendering, and slow capture remove
the effect. Pointer and wheel input cancel it and route to the current underlying owner.

A pointer press on the cover reveals the destination without forwarding the press
to an unseen control. A fresh press is required to activate destination content.
The native regression exercises an actual shared button beneath the cover and a
fresh-action positive control; programmatic Tk input is not physical input proof.

The two appearance observations, transition_shown and transition_skipped, carry no content
or screen data and are bounded once per transition-owner lifetime. The existing telemetry
owner still enforces consent, provenance, schema, and session delivery limits.

## Detail navigation and saved versions

Library details provide one quiet, labeled Back action that returns to the actual
origin. A saved-version selector appears only when that item has multiple saved versions.
The shared ChoiceDropdown resolves the selected version by current record identity;
changing versions preserves the browse origin and never repurposes another item's edits.
Watch See All keeps its channel context and retains route, query and scroll in its
origin stack. Opening a playlist clears the active search; Back restores the
original results. The shared search field reflects the active view's own query
without applying it to another view.

Mac native transport controls use the shared palette for hover, focus and press feedback.
Action glyphs use the icon role, both progress rails use the progress role, and
time/notice labels remain neutral. The existing presentation poll refreshes native
controls only when their palette changes, including while playback is paused.
AppKit receives explicit sRGB colors. Native-pixel assertions convert the captured
display-profile bitmap to sRGB before comparing with those tokens.
The earlier shared Tk theme fixture did not cover this AppKit adapter and missed
hardcoded white glyphs and purple/white rails. Actual MP4 playback now checks
rendered glyph/rail pixels through changed and restored roles, alongside existing
provider, menu, fullscreen, volume and callback-retirement outcomes. This does not
replace responsive layout, external accessibility or physical-input evidence.
Disabled controls retire their highlight; hidden controls draw none. This adapter belongs
to platforms/macos/player_overlay.py and is driven by the existing overlay update loop. The source
state test and native MP4 pointer/volume test cover the adapter separately from installed
package acceptance.

## Contextual selection and file decisions

Library browsing shows Select. Selecting items reveals a count, Actions and Done.
Actions contains Add to Collection, Move to and Delete for the captured selection;
ordinary browsing gains no permanent file-management toolbar. Single-item menus
route to the same captured-owner coordinator. Collection saves preserve the actual
browse origin.

FileActionDialog uses ActionDialogSurface, shared button variants and scoped
Return/Escape. Move shows destination, eligible count and conflicts before committing.
Delete distinguishes existing files from missing Library entries. System Trash is
the default; unavailable Trash requires a separate explicit irreversible confirmation
for permanent deletion. A failed Trash action never changes that choice.

An interrupted change gets a focused review dialog with source/destination folder
actions, Finish move when publication can be verified, and Keep as is. Recovery
internals stay in private diagnostics. Essential footer actions remain visible.
Closing a running file decision requests cancellation without retiring its eventual
durable result. The source-native dialog tests cover real fixture Move, mixed Delete,
declining permanent deletion, and Escape after the confirmation becomes ready.

Locations keeps its plain heading. Discovered volume/share names have quiet
Local, External or Network subtitles; unknown types remain explicit. Duplicate
names have distinguishing path suffixes and a full-path tooltip. Canonical path
identity, rather than the displayed label or list index, owns selection.
The player's Recent row also uses SceneRail and its complete keyboard endpoints.


### Raster surface ownership on macOS

Native field checks read captured RGB pixels rather than assuming every Tk image
supports PhotoImage's pixel API. Same-size palette and state changes preserve the
live image handle: idle faces remain neutral, material changes repaint, and focus
adds then removes the bounded rounded contour. The previous neutral-field test
expected image replacement and no focus change, so it missed this contract.
Actual wrong-accent and stale-theme transport faults are rejected by rendered
pixel checks; the density suite independently rejects missing, stale and
rectangular focus and a low-resolution producer. These are representative
source-native checks, not external accessibility or installed-runtime evidence.

CanvasSurfaceCache retains the approved gradient, illumination, and rounded-edge
bitmaps. On supported Retina Tk runtimes, platform_services creates the public
nsimage representation at physical pixel resolution, leaving text and icons in
their existing owners. Temporary AppKit image names are unregistered immediately
after Tk takes its copy. Windows, non-Retina displays, and unsupported runtimes
keep PhotoImage rendering. Cache keys include physical scale; byte accounting
includes scale squared and both native representations. Visible images remain
owned even when reusable entries are evicted. Sidebar and action surfaces use
the same cache class with separate canvas ownership.

A retained Python image wrapper is not proof that its Tcl image still exists.
If reuse fails, CanvasSurfaceCache confirms that the image is actually absent,
retires that entry from the reusable and in-frame caches, and rebuilds it.
Unrelated canvas errors and failures of newly created images still propagate.
Rebuilt oversized surfaces remain borrowed only until the current frame ends;
they do not expand the reusable byte budget. Existing presentation observations
report fault, recovered and settled for the same operation when rendering repairs it.


Native fidelity checks compare full and regional pixel differences, including
text, glow, and curved edges, and verify release of Tcl/native names. Simulated
scale changes test cache invalidation; moving a live window between physical
displays still requires separate device evidence.


Mac scrolling through canvases containing child viewports services at most six
nonblocking Tcl idle batches after the complete two-axis/ancestor dispatch, with
a 40ms scheduling budget checked between batches. Individual idle callbacks cannot
be preempted; this is not a hard 40ms execution deadline. Input and timers are not
processed by this seam. Geometry can queue drawing in a later batch.
A toplevel guard prevents recursive drawing drains. All target actions finish
before this seam; an idle callback may destroy or replace the view, so no retired
target is touched afterwards. Native regressions cover nested input, both axes,
owner replacement/destruction, and callbacks that schedule more idle work.

## Whole-control audit and remaining acceptance

The [control-family inventory](../engineering-quality/acceptance/UI_CONTROL_FAMILIES.json)
records direct constructor calls and declarations across the application. Families
overlap: a dropdown owns a popup, for example. These are static candidates, not
proof of runtime reachability or accidental duplication. A class with no direct
constructor still requires subclass, factory and dynamic-reference review before
removal.

| Family | Existing owners/adapters | Outstanding qualification |
| --- | --- | --- |
| Ordinary labeled actions | ui_button_contract, ttk chrome, ScenePainter | Representative default/spec-change parity passes; all states, platforms and branches incomplete. |
| Icon/navigation/player actions | RoundedIconButton, shared ttk showcase navigation, PosterPlayButton, PlayerTransportButton, CanvasActions, native player overlay | Independent implementations and activation differences need review; five scene icon metric overrides remain. |
| Text/search/editing | ProductEntry, PlaceholderEntry, LibrarySearchField, EditableTextSection, FactsText, ActivityLogText | Search composition and editable/read-only/log roles differ legitimately; shared metrics, placeholder/focus/selection and raw Entry/Text bypasses need qualification. |
| Choices/segments | ChoiceDropdown, ChoiceMenu, ChoicePopover, SegmentedSelector | Shared choice ownership exists; spec propagation, disabled options, popup retirement and preview reuse remain to audit. |
| Toggles/radio | ModernCheckbox; radio-like SegmentedSelector choices | Shared checkbox now commits pointer intent on release and retires disabled gestures; frame/box/label native checks pass. Full generated/spec propagation and every consumer remain incomplete. |
| Tabs/mode navigation | ttk notebook and styled nav buttons, ActivityModeSlider | Selection, focus and consistent sizing need cross-view evidence; a mode selector is not a seek slider. |
| Seek/volume sliders | media_player_ui canvas transport and platforms/macos/player_overlay.py | Separate platform adapters must share intent/disabled/drag lifetime contracts; no claim that input mechanisms are interchangeable. |
| Scrollbars/scroll routing | SleekScrollbar, ScrollBinding, SceneRail | Two-axis routing/lifetime checks exist; sustained response, physical devices and complete spec propagation remain open. |
| Menus | tk.Menu, ChoicePopover/ChoiceMenu, RunHoverMenu | Native context menus and in-window choices have distinct placement needs; owner retirement, keys, focus return and duplicate custom implementations need audit. |
| Dialog/focus/keyboard | ActionDialogSurface, KeyboardScope, direct Toplevels | Protected footers/scoped keys have representative checks; remaining popup bypasses and focus restoration need full inventory review. |
| Lists/tables/selection | tk.Listbox, ttk.Treeview, ChapterList, PixelScrollTable, scene catalog targets | Selection semantics, virtualized ownership, keyboard access and live/unused paths need review; no global shared-component acceptance yet. |

### DPI and label qualification within the same inventory

The intended scope includes every enabled control **and label**, not only buttons.
The family inventory above remains canonical. This finite DPI overlay records
implementation boundaries; none of its rows establishes whole-app adoption.
Production Windows PMv2 remains off until the enabled consumers agree on units.

| Consumer group | Existing boundary | Current DPI status / next proof |
| --- | --- | --- |
| Static labels, headings, captions, inline values and readonly documents | ui_theme font roles, ui_styles, ScenePainter, FactsText, ActivityLogText | FactsText and ActivityLogText now use per-window fonts/canonical spacing with exact-font measurements; bounded macOS default/injected2x text, reflow, selection and severity-label checks pass. Static labels/headings/captions and whole-app/Windows adoption remain unverified. |
| Ordinary action buttons | ProductButton, ButtonMetrics, ProductChromeOwner | Fixed96/192 opt-in variants pass bounded Mac native geometry, focus, palette restoration and lifetime checks. Prior88/86 failure retained; exact-tuple font measurement repaired it. Actual Windows and remaining aliases unverified. |
| Top/sidebar/mode navigation | shared navigation material, CanvasActions, ActivityModeSlider, notebook styles | Representative no-underline concavity accepted on Mac. DPI/icon/text bounds, selected/focus/disabled state and all consumers remain unverified. |
| Text/search/editors | ProductEntry, PlaceholderEntry, LibrarySearchField, editable Text owners | Bounded entry192-DPI geometry/edit/lifetime proof exists. LibrarySearchField now scales entry/placeholder/hint fonts, search glyph and padding through the existing window metrics; default/injected2x editing, compact mode, focus material, border clearance and retirement pass on Mac. PlaceholderEntry now inherits the entry font, scales its hint inset and matches focus material; bounded default/injected2x plus real collection keyboard checks pass. EditableTextSection uses per-window fonts/spacing/icons; default/injected2x draft failure/retry/cancel and calculated-height/footer checks pass, including settled error feedback. Actual Windows, remaining readonly consumers and popup inheritance are unverified. |
| Choices and segments | ChoiceDropdown/Menu/Popover, SegmentedSelector | Bounded dropdown/menu192-DPI proof exists; v95 direct native font-width/ellipsis checks pass at default/injected192 without a ChoiceMenu runtime change. SegmentedSelector now scales exact-font labels, padding and backing-density surfaces; bounded Mac 2x geometry/release and nine existing input cases pass. All labels, disabled options, actual Windows and every consumer remain unverified. |
| Checkboxes and radio-like controls | ModernCheckbox, SegmentedSelector | Checkbox box/label/glyph unit conversion and backing-density raster pass bounded Mac default/2x checks and pointer retirement cases. Bounded 2x segment label/selection proof also passes; actual Windows and every consumer remain unverified. |
| Player actions and seek/volume sliders | transport/poster adapters, native video host and Mac overlay | PlayerVolumeControl now scales geometry, track/thumb and pointer insets together; default/injected192 exact0/50/100 input,5-step callbacks, focus/restoration and retirement pass. PlayerTransportButton icons use window units/backing adapter and preserve Play/Pause refresh. SleekProgressbar bounded default/injected192 fraction/track/timer-retirement checks pass. Timeline pointer math and coupled transport units are repaired in source with headless endpoint/current-media tests; default/injected192 native endpoint/maximum-heatmap/transport-row checks now pass in the33-case v103 dependency suite, including existing stale-media retirement cases. Full player layout, native overlay/rehost and actual platform input remain unverified; PiP delivery gap remains. |
| Scrollbars, lists, tables and chapters | SleekScrollbar, PixelScrollTable, Treeview/Listbox/ChapterList, SceneRail | SleekScrollbar default/injected2x track/thumb/stroke and fractional dragging pass bounded Mac checks in both orientations; existing retirement/input cases pass. ChapterList now uses a variant of its existing native style for per-window row/font dimensions and scaled fixed columns; default/injected192 selection, final-row scrolling, theme refresh and sibling isolation pass on Mac. Existing ordinary OS-key list focus checks pass. PixelScrollTable is not constructed by current production code and was left unchanged; Active folder/location constructors now use the same per-window native-style derivation as chapters;6 bounded row/font/input cases pass including chapter isolation. The location screenshot exposed its fixed184px sidebar clipping the larger list; coupled sidebar width/padding/headings and viewport bounds now pass the33-case v103 dependency suite; the corrected2x capture is readable. Collection editor Listbox, labels, spacing, wheel-row units and popup minima now use that popup's own metrics. Default/explicitly injected192 list geometry, last-item pointer selection, failed-save retention/retry and minimum-size error/footer containment pass; the existing ordinary OS Return/Escape/grab journey also passes. Screen sizing reuses bounded_window_size; native popup admission, physical monitor/work areas and Windows remain unverified. |
| Menus and popups | native tk.Menu versus owned ChoicePopover/RunHoverMenu | RunHoverMenu now uses its existing ChoicePopover window metrics for width, rows, padding, scroll increment and one exact drawn/measured font. Default/injected192 above/below containment, fitting/ellipsized Unicode labels, last-row dispatch and off-viewport retirement pass in11 bounded Mac native cases including shared choice lifecycle controls. Native tk.Menu, physical monitor/work-area behavior and RunHover focus return remain unverified. |
| Dialogs and protected footers | centered_toplevel_geometry, ActionDialogSurface, existing Toplevel constructors | Canonical sizing helper has1x/2x and measured-height source tests. ActionDialogSurface now scales canonical shell padding, footer/status gap and scrollbar spacing from its own window metrics. Default popup remains independent of injected2x parent; explicitly injected2x popup passes native protected status/footer and action checks. Automatic native-popup DPI admission, minima, work-area containment, labels and full enabled-dialog journeys remain unverified. |
| Tooltips and transient hints | _TooltipController/ToolTip and entry hints | Default/2x Mac tooltip font/wrap/offset and owner-hide dismissal pass. Pointer presence is controlled in this fixture; real delayed pointer journeys, monitor containment and every hint consumer remain unverified. |
| Icons, artwork and themes (cross-cutting) | shared icon loaders, surface adapters, theme palette and bounded caches | Bounded native192-DPI raster/theme proof exists. Whole-app sharpness, all consumers, actual fractional/mixed-monitor changes and Mac contour sharpness remain unverified. |

Remaining implementation owners after v100 (this refines the same finite inventory):

- Scene geometry/typography and navigation: ScenePainter, LibraryScene, Watch/PlayerScene, top/sidebar/mode consumers. SceneRail owned scrollbar reservation and gap now have bounded v121 default/injected192 viewport, final-target dispatch and retirement proof, with existing Watch/Player consumers passing. Caller allocations remain measured; full caller card/text conversion is pending. Shared material/style primitives are bounded; whole-scene unit conversion is not.
- Active archive list consumers: location/folder Treeviews and coupled sidebar have bounded v103 qualification; collection Listbox and its dialog have bounded v120 default/injected192 and ordinary OS-key qualification. Native-popup admission, physical/platform-wide acceptance and broader dialog consumers remain separate.
- Player remaining consumers: seek/progress, complete transport layout, native Mac overlay/video host/rehost. Volume and transport icons have bounded local proof; no full-player claim.
- Static labels and dialog contents: ui_styles/classic label consumers, per-dialog spacing/minima/work-area and actual native Toplevel DPI admission. Collection v120, annotation v122 and missing-media recovery v124 content have bounded default/injected192 proof. Recovery preserves measured height and exact recovery actions; actual relinked-media cases also pass. Annotation ordinary minimum now preserves note visibility; enlarged metrics reuse the existing scrolling body with focused-field reveal. Shared entry/editor/shell conversion is bounded; remaining dialogs and physical acceptance stay open.
- Menus: native tk.Menu fonts/placement and RunHoverMenu focus-return/physical-monitor coverage remain. RunHoverMenu default/injected192 content geometry and existing ChoicePopover containment/retirement now have bounded v119 proof.

Coop's September19 follow-up explicitly includes header/app marks, in-app emblems,
Dock and Windows taskbar icons. These are cross-cutting brand consumers of the
same window/raster units, not a new UI owner. Asset/container fidelity, source-native
sharpness, actual Windows physical DPI and installed Dock/taskbar identity require
separate receipts. Windows qualification now proceeds on an immutable source
snapshot in parallel with Mac fixes; production DPI admission remains off.

### Current bounded DPI progress, v136–v137

Root Forge now uses window units for static fonts, layout thresholds, run-deck
capacity, artwork, overlays and padding. At the actual 820×560 minimum, measured
rows can place destination and local conversion on separate rows; URL and
control targets remain usable. Real portrait media retains its fitted aspect;
placeholders and icons use the existing native backing adapter. Native default
and injected192 checks cover narrow/wide/return, empty copy and action reachability.
Library sidebar and home/browse cards scale their text, artwork, hit targets and
material together through existing scene options. Sidebar is physically verified
on Windows192; center-card/menu/empty interactions are being qualified there.
Library detail, Watch and Player remain separate consumers.

OutputDetailsDialog has bounded local default/192 proof for its own window fonts,
minimum/wide/return layout, title wrapping, lossless scrollable document and stable
Done footer. Native section tags remain aligned. These slices do not complete the
full finite inventory or packaged/platform gates; production admission is off.

### Remaining enabled DPI work items after v125

The original15 named work items below have14 remaining after v126 qualifies item6
locally; app embedding remains in item5. These are groups of coupled
owners, not a widget/dialog count or a new acceptance matrix:

1. ScenePainter shared scene fonts/geometry, coupled to its callers.
2. LibraryScene/LibrarySceneLayout/LibraryDetailLayout cards, details and actions.
3. WatchView/WatchSceneMixin cards, horizontal sections and actions.
4. MediaPlayerWindow/PlayerSceneMixin complete layout, video host and Mac overlay.
5. DownloaderApp._build_focus_ui and _build_focus_forge_view: root navigation,
   static labels, mode/side controls and canonical spacing.
6. **Locally qualified v126:** ForgeActivityPanel/ActivityModeSlider mode geometry,
   pointer midpoint, control/log allocation, keyboard/drag retirement and lossless
   content. Root embedding remains item5; physical/integrated acceptance is open.
7. **Locally qualified v138:** FocusSettingsDialog own-window fonts/minima, measured
   column reflow, all three output modes, viewport and protected footer. Physical
   Windows popup admission/interaction remains open.
8. **Locally qualified v137:** OutputDetailsDialog own-window fonts/minima/title
   wrap, lossless document scrolling, section tags and protected Done. Physical
   Windows popup admission/interaction remains open.
9. DownloaderApp._show_selected_metadata_details content/shell.
10. LocalAudioVideoDialog contents and protected progress/actions.
11. SupportPanel feedback/review plus its diagnostic-review child, one existing owner.
12. FileActionDialog move/delete contents/status/actions.
13. show_update_recovery contents/path/actions.
14. WhatsNewPanel ONLY the enabled EngagementController.welcome path; automatic
    What's New/Did You Know remains SHOWCASE_MODE=none and is not re-enabled.
15. ContextMenu native tk.Menu font/placement/platform authority. Mac native menus
    may own their font behavior; do not force injected scaling blindly.

Active construction is grounded in app.py, library_file_actions_ui.py,
engagement_ui.py, analytics_startup.py and their current scene builders. Completed
component slices remain bounded; their native popup admission and full consumer
interaction still need integration. PixelScrollTable/RoundedIconButton remain
unused and excluded. No open-ended conversion of dormant surfaces.

Recommended order: core work items1-6 as coupled existing-owner batches, then
settings/details/local conversion7-10, support/file/update/welcome11-14, and native
menu authority15 alongside platform admission. Before production admission, run
one bounded integrated app sequence at default/injected192 through these enabled
owners, then the exact source on actual Windows with its existing guarded HWND
DPI adapter. Verify initial physical scale, real pointer/keyboard, modal ownership,
monitor transition behavior and native video/menu contracts; explicitly leave
fractional/mixed-monitor cases unverified where the machine cannot exercise them.
Coordinate foreground/readiness before Windows temporal/physical work. Mac injected
proof is not a substitute. Resize remains parked; original85/platform/package
requirements remain separate and cannot be waived by this queue.

PixelScrollTable and RoundedIconButton have no production constructor calls in the current source (the latter retains a compatibility alias); they were not converted speculatively. This inventory excludes the independent remaining physical-monitor, Windows, accessibility, packaged/install and original acceptance gates.

Canonical dimensions convert once at their shared owner. Measured coordinates,
font measurement results, native window bounds, ratios, character counts and time
values retain their respective units. Recovery dialog requested height is already
measured and explicitly bypasses height conversion. Do not treat a global DPI flag,
blanket multiplier or Tk scaling change as completion of this inventory. Physical
Windows fractional/mixed-monitor evidence, exact package manifest policy and
installed behavior remain separate gates from these source-level adaptations.

For each row qualify before/during/after states and shared-spec-change propagation.
Required cases include disabled/no-op actions, hover/focus/press, hit areas,
release outside, owner replacement, keyboard activation, empty/long content and
narrow views. Preserve specialized behavior when it serves a real task; move
accidental copies into existing owners. Counts and generic passing tests cannot
close this matrix. Telemetry may record bounded actions/outcomes and safe causes,
but never entered text, content, paths or raw input.

Showcase Previous/Next now use labeled shared ttk secondary actions. The removed
_ArrowButton activated on mouse-down; the maintained native check asserts no
navigation on press or release outside, plus disabled and normal invocation.
This closes that specific bypass, not the whole icon/navigation family.

ModernCheckbox retains one owner across settings, support and native feature
previews. Pointer press captures the current variable/command without changing
the value; valid release commits once. Release outside or disable/re-enable
retires the gesture. Keyboard activation stays on the existing shared toggle
path. Three native regressions failed before the change and pass afterward;
the combined native UI-polish/shared-controls/showcase run passed 76 cases.
This does not close all toggle or control-family acceptance.

SegmentedSelector's compact, ordinary and separated layouts share pointer
admission. Press does not change selection; release must belong to the same
visible segment and variable. Hiding a segment retires the gesture. Return and
Space retain the existing keyboard path. ProductButton and ModernCheckbox also
retire held pointer intent on unmap, including a hide/remap cycle before release.


### Choice option lifetime

ChoiceDropdown owns the option snapshot behind its open ChoiceMenu. Replacing,
emptying or reordering values retires that menu before any queued pointer or
keyboard selection can commit. Reapplying an identical option sequence preserves
the current intent. Current enabled state and popup identity remain commit guards.
A later valid choice continues to work; context-specific selected values and
callbacks stay with their caller.

The three stale-option regressions failed before the shared-owner repair. The
subsequent 92-case native shared-control, UI-polish and button-parity run passed,
including the identical-options positive control. These are real Tk widgets with
an explicitly simulated queued callback at the commit boundary, not physical
input certification or complete all-family coverage.


### Scrollbar drag ownership

SleekScrollbar is the common horizontal/vertical thumb owner. A held drag remains
active when the pointer leaves its narrow track; leaving changes hover only.
Mouse release, widget/ancestor unmapping, or content becoming fully visible retires
the drag. Remapping or restoring overflow requires a fresh press. A drag may
change only its bound axis and must not borrow another viewport's state.

The enrolled shared-control native suite covers both axes, hidden-parent and
content-fit retirement, and valid fresh successors. Quartz-input checks drive an
actual Canvas outside the track and after release, assert the other axis and
window geometry remain unchanged, and require movement during the pressed
interval. Reinstating the previous Leave handler makes both OS checks fail.
These are source-native input and ownership checks, not sustained smoothness or
physical-device acceptance.

The first OS fixture accidentally placed a thumb on the native window-resize
edge. Its nominal pass is explicitly invalidated and retained with a native
stack sample. The corrected fixture is inset from window chrome, input posting
runs independently of the UI event loop, and the geometry assertion detects
that fixture error.


ActivityModeSlider retains its continuous two-position disclosure behavior, but a
pointer sequence now belongs to the action captured at press. Release, unmapping
and callback replacement retire that sequence. A later motion cannot change the
new disclosure owner; fresh presses and keyboard Up/Down remain available.
The enrolled activity suite includes three before-failing retirement regressions
with fresh-pointer and keyboard positive controls. This is behavior qualification;
the current bespoke renderer is not claimed to be consolidated with other
selection controls.


### Progress feedback lifecycle

SleekProgressbar owns its variable subscription, initial idle redraw and active
animation timer. Destruction retires all three, without deleting or rewriting
the caller's variable. Late start/redraw work cannot restart a destroyed
indicator. The native contract inspects Tcl's pending work and variable traces
and then verifies a fresh indicator still displays the shared value.

The control-family inventory now includes progress feedback explicitly, alongside
the prior ten families. Direct constructors are a starting point: Canvas-drawn
progress, other feedback adapters, state parity and complete cross-platform
qualification remain unproven. Three native before-failing cleanup cases and
working-successor controls do not certify all progress presentation.

CanvasActions likewise retires captured press and hover state on unmapping,
including ancestor hide/remap. Keeping the same callback tuple across navigation
does not authorize an old release; a fresh press is required. Two native
before-failing regressions cover direct and ancestor hiding.

## Bounded text fitting

Library and Watch keep using the shared ui_layout ellipsis fitter. Its internal
line predicate stops after the visible line budget is exceeded; it does not
measure every invisible wrapped line of a long title. Full document layout still
uses the exact measured_wrapped_line_count API. This changes work, not truncation,
fonts, artwork or visual treatment. The readable_descriptions scenario enrolls
independent exact-capacity and work-budget regressions. Real-font differential
checks retain the original fitted strings. Native resize completion remains a
separate unresolved acceptance claim; lower fitting cost is not smoothness proof.

## Native backing resource qualification

CanvasSurfaceCache counts distinct retained images and limits unused reuse to
8 MiB; those counters do not measure all native runtime allocations. The Mac
native suite separately observes process RSS during warmed replacement cycles
and after teardown. Tk 9.0.4 currently fails that check despite retiring Tcl image
names. The diagnostic raw RGBA transfer was reverted; the application retains
its prior PNG-native transport while the runtime defect and release options are
investigated. An isolated patched Tk result does not qualify the shipped app.
See the engineering guide's native resource workflow and preserve the failing
runtime, positive patched control and actual loaded-library identities.

### Visible keyboard orientation in segmented choices

SegmentedSelector renders a darker concave focus material inside the existing option surface.
Focus changes invalidate that option's raster independently of selection and
hover, without changing layout dimensions or changing the bound value. Focus
out restores the ordinary surface; the no-image fallback uses the same semantic focus value without an underline.
All three layouts use this shared behavior. The native pixel regression observes
unselected and selected focus, verifies restoration and unchanged dimensions,
and separately checks Space activation. These source-native captures establish
visible feedback, not physical-keyboard or complete accessibility acceptance.

### Run menu execution ownership

Cancel run, Skip current item and Skip current source URL capture the DownloadJob
instance that opened the run menu. A queued callback is admitted only while that
same execution is active. Completion, successor admission, an equal-but-distinct
job, or an already-stale row cannot redirect it. Mutable render dictionaries are
not command authority. Fresh commands remain usable. Source-native tests invoke
the actual Tcl menu command boundary; they do not claim OS menu placement/input
or within-run item rollover qualification.

### Native context-menu lifetime

ContextMenu extends Tk's native menu and owns one current popup per native window.
All 15 direct construction sites now use it (13 roots and two cascades).
A replacement destroys the old menu and cascades, releases their Tcl callbacks
and owner binding, and makes a queued old Python callback inert. Hiding the
source widget also retires its menu. Separate native windows retain independent
menus; cascades share their parent's lifetime.

A return from tk_popup or unpost is not automatic destruction: Windows can
deliver the selected callback afterward. The still-current session remains
available until replacement, owner hiding or explicit destruction. Existing
dismissal APIs are idempotent so a menu callback can open its successor safely.
This owns presentation lifetime only; each action must still validate its
captured execution/media subject at commit. ChoiceMenu/ChoicePopover and
RunHoverMenu retain their distinct in-window presentation roles. Native
placement/input, all specialized consumer outcomes and Windows qualification
remain separate from the bounded lifetime tests.

Watch's View in Library menu action also captures the original media subject.
The existing archive subject resolver finds its current index after projection
reordering; a removed subject cannot redirect the command to a neighboring
video. Menu lifetime and media-subject validity are separate guards.

### Volume keyboard focus

PlayerVolumeControl is shared by the Canvas player transport and the What's New
player preview. Keyboard focus recesses the existing trough with the shared field material,
within existing dimensions; the knob keeps its normal foreground. Focus entry/exit changes pixels without changing
volume or invoking the provider. Its rendering signature includes focus and
palette tokens, so value-only caching cannot hide the indication.

The native focus regression captures before/during/after at zero, middle and
maximum volume, verifies exact restoration and a second control's unchanged
pixels/value, exercises a keyboard adjustment, and checks trace cleanup.
All three cases failed before the shared owner fix. This qualifies that Canvas
adapter's bounded focus behavior. The native macOS overlay and physical input
remain separate adapters/tiers. Focus alone emits no new usage event; actual
volume changes retain the existing playback observation path.

### Destruction releases variable ownership

ModernCheckbox, SegmentedSelector and ChoiceDropdown must release their retained
Tk variables during UI-thread destruction, after detaching traces and retiring
pending input. A dead widget can remain in a Python child/owner cycle; it must
not keep the variable alive until an unrelated worker triggers collection.
Checkbox commands and captured press state are retired as part of that boundary.
This does not destroy an externally owned variable or change another instance's
binding. Post-destruction queued activation is inert.

The native weak-reference regression distinguishes a sole control owner from a
caller retaining the variable. Three before-fix failures and three valid external
ownership controls are retained. The corrected six cases pass without a GC call.
Native qualification treats unexpected finalizer/thread warnings as failures.

### Modal return and retired recovery actions

ActionDialogSurface with modal=True owns restoration of the preceding local grab
and visible keyboard target. Destroying an older dialog must not steal focus or
grab from a newer modal. A missing or hidden former target is not focused.
Collection and file-action dialogs use this shared contract; update recovery now
uses it too, together with the surface's scoped Escape binding.

Update recovery retires its parent-resize binding and all decision callbacks on
Later, Escape, successful repair admission or external destruction. Repair is
admitted at most once from that popup. A queued action from a closed popup cannot
start repair, open a browser or expand destroyed controls. Tests replace repair
and browser effects with controlled callbacks, so no real update is downloaded.

Native checks cover actual focus/grab before and after, nested and successor
modals, a destroyed origin, the existing Toplevel consumers and the in-window
recovery surface. The inline focus case and all three original recovery closure
cases failed before adoption. These are bounded navigation/lifetime checks, not
physical keyboard or packaged-update qualification. No passive focus telemetry is
added; admitted repair continues through the existing updater observation path.

### Player input retirement

MediaPlayerWindow owns admission of seek, relative seek, timeline, chapter,
preview and volume callbacks. Closing the window, including external destruction,
retires these inputs before widget access, provider calls or feature reporting.
The closed flag is the existing session owner; do not create a second callback
lifetime. Play/Pause already follows this boundary.

test_player_action_retirement_native.py exercises six callbacks with explicit
close and external destruction. Each callback first reaches the controlled
provider while live; its retained Python callback becomes inert after close.
The real chapter/timeline widgets expose stale Tcl access. The pre-fix twelve
failures are retained in player-retirement-before-v9. These checks use real Tk
widgets and a controlled provider; they are not physical-input, codec or package
qualification. They are enrolled in the source-native suite on supported hosts.

The macOS overlay explicitly imports Quartz before requesting NSColor.CGColor.
This registers the Core Graphics reference bridge without relying on another
view's import order. test_player_macos_bridge.py checks that path in a fresh
process with warnings as errors; it needs no native window. Preserve the native
color and reference ownership rather than suppressing ObjCPointerWarning.

Media-bound player input also checks the captured backend, load generation and
path before touching old chapter/timeline widgets. Same-path reload is a new
generation. Current relative keyboard seeking is deliberately distinct from an
old absolute timestamp; closing retires both. The successor matrix covers
different-path load, same-path reload and backend replacement with valid
original actions and valid current relative controls. Removed old chapter/timeline
widgets must never be accessed during rejection. This is a serialized UI admission
contract, not a claim about arbitrary concurrent provider mutation.

Quartz is now an explicit macOS requirement pinned alongside Cocoa at12.2.2.
Its import is bridge initialization, not a warning suppression or color change.

### Search and placeholder field retirement

PlaceholderEntry and LibrarySearchField release their variable references after
removing only their own trace on destruction. Caller-owned variables remain usable.
Search cancels its initial idle refresh; retained refresh, focus, compact-layout
and theme callbacks become inert before touching destroyed widgets.

RoundedFieldBorder owns its raster and Configure/Destroy bindings. Destruction of
either its field or canvas releases the Tk image on the UI thread and retires
later drawing requests. Other field instances retain their own images and behavior.
The shared-controls native matrix holds destroyed owners alive deliberately,
checks weak references without forced collection, exercises external variable
ownership, and verifies pending idle cancellation and independent surviving chrome.
The two variable and two image-retention pre-fix failures remain diagnostic receipts.
These are lifecycle assertions, not complete editing/paste/accessibility acceptance.

ProductChromeOwner keeps interpreter-wide style images until its actual root is
destroyed, then releases them on the UI thread and ignores late requests.
Child-window destruction must not retire shared styles. The native root-lifetime
regression checks both boundaries while keeping the Python owner alive.


Native window lookup resolves the current widget's Tk ID and native window on
each call. Only the process-library function binding is reused; window/view
objects are never cached by this adapter. Failed symbol resolution can be retried
after Tk loads, and a destroyed control still reports unavailable. This avoids
repeated library/symbol setup during surface rendering without changing ownership.

### Saved-location review

The return action reads **Back to Library**, including after a cancelled or
refused update. Escape within the review uses KeyboardScope and the same relink
cancellation action. During a pending save, Escape and Library/Watch navigation
request cancellation and keep the review visible while storage confirms the
outcome. They must not destroy its controls or discard the completion callback.
The existing waiting status explains why navigation has not yet occurred. Once
storage settles, the user can navigate again; a completed save is shown truthfully.

The item's **File found** label reports verification only. The existing review
status owns the current update phase: saving, cancellation requested, or a
confirmed outcome. Pending cancellation must not imply either success or that
nothing was saved. Use plain Library/location wording instead of relink/history
internals. A refused submission must replace the saving message with a retry route.

A finished file check must retire both its pending headline and pending item
labels. Verification failures show an unavailable state; timeouts show File check
took too long and a plain return/retry instruction. Rendering a timeout must not
change the original verification proposal or make any file eligible for an update.
Closing an already settled review dismisses the view; it is not a new cancellation.


## Preparing a sibling review

WidgetReveal in ui_transition.py keeps the outgoing Library widgets visible while
the relink review or initial player loading panel reaches its requested geometry.
The panel owner supplies a current-owner predicate, a scoped Escape action and,
when needed, a final-layout predicate. Call start only after constructing the
panel. This is ordinary event-loop staging, without a screenshot, blur or nested
event pump. It does not share the top-level tab transition's mutable state.

During staging, temporary bindtags guard only the outgoing subtree. The
ViewInputRetired virtual event retires existing CanvasActions and ProductButton
gestures before those tags are installed. Navigation outside that subtree remains
available. Cancellation removes only this reveal's tags, callbacks and timer;
the view owner still owns destruction and restoration. Class bindings register
Tcl callbacks on the root, so cleanup must remove them from the root's command
registry as well as clearing the binding.

The native lifecycle check covers cancellation, destruction, supersession,
successful reveal, scoped Escape, stale button/canvas release and intentionally
hidden content branches. The independent Quartz frame check
covers a relink verification refusal and deliberately pending playback resolution,
including return to Library. Entry and return have separate actual fault controls;
sparse loading text is also checked in measured control regions. Neither is a
whole-player, actual video, physical-input, Windows or packaged acceptance claim.


The same owner stages the return beneath the outgoing review/loading panel.
An incoming sibling group may be supplied. Intentionally unmanaged branches,
explicitly hidden canvas window items, offviewport canvas windows and hints placed
relative to those excluded windows do not participate in current readiness. Tk
can keep these widgets unmapped until a later scroll; waiting for them indefinitely
would leave the outgoing panel covering an otherwise ready Library. Visible
managed descendants still require mapped, usable geometry, and the owner's
final-layout predicate remains authoritative. The finished callback runs once on reveal or
cancellation, after owned bindings and timers retire. The archive owner uses it
to destroy the outgoing panel and clear its pending restoration. New overlays,
tab changes and shutdown retire that restoration; a stale completion cannot
cover a newer view. This is presentation lifetime only, not a second navigation
or playback state machine.

The v61 default Library regression retains the original surviving-error-cover
failure and verifies OS dismissal, unchanged action/history/queue state and fresh
intended second-item input. Generalized hidden-item/offviewport/placed-hint cases
fail against the old readiness walk. Each also holds a genuinely visible one-pixel
control unready, then permits reveal only after usable geometry. Existing
cancel/destroy/supersede/Escape/stale-callback cases and playback/relink consumers
retain their lifetime checks; exclusion is not a timeout or readiness bypass.


## Readonly native lists: selection and keyboard focus

`ui_styles.apply_product_styles` owns the shared selection maps for
`ArchiveLocations.Treeview`, `Archive.Folders.Treeview` and
`Player.Chapters.Treeview`. The consumers are Library locations, folder ancestry
and `media_player_ui.ChapterList`; Settings does not contain a Treeview.

A selected row with keyboard focus uses `accent_dark` and neutral `on_accent`
text. Retained selection after focus leaves uses `accent_surface` and neutral
`text`. These existing lavender-family roles distinguish current keyboard focus
without changing row values, navigation, selection, readonly behavior or list
implementation. Keep the two states in the shared style owner; do not add local
selection colors or replace the native list to obtain focus feedback.

The maintained shared-controls regression measures actual selected-row RGB
regions before/during/after focus, moves selection with OS Down and checks that
OS text input cannot edit readonly rows. Withholding focus must retain the exact
unfocused rendering. All three cases failed under the former selected-only maps;
older chapter tests checked selection and values but not rendered focus. Current
v63 evidence includes existing segmented-control and player-volume focus cases.
This qualifies one theme and representative native adapters, not every full
consumer journey, theme, platform, physical input or external accessibility.

## Approved brand artwork

Use [the canonical branding guide](branding.md) for the exact matte VF artwork,
source-pixel export workflow and platform assets. Do not replace rich artwork with
a polygon approximation. The current statement is “Your media. Your way.”

## Matte material and shared-control contract (September 19)

The current direction is a deliberate tactile monochromatic design, not a
desaturation filter. The newer request supersedes the earlier Library texture
omission. Each theme retains its hue, with softly raised actions, recessed fields
and tracks, restrained panels, and distinct pressed/selected/focus/disabled states.
One upper-left diffuse light convention lives in the material renderer. Shadows
remain inside existing control bounds; click targets and documented metrics do
not change. Hover retains its idle face and contour colors while increasing the
shared inset depth; it never adds a local border highlight or brighter fill.
Never add a screen-local shadow, hover renderer, or palette copy.

| Authority | Owner |
| --- | --- |
| Monochrome material palette plus separate foreground semantic roles | ui_theme.py |
| Raised/inset face, primary paint, focus, directional edges, shared tracks | ui_chrome.py |
| Static motif masks, frame/canvas adapters, app-only logo tint | ui_materials.py |
| Button metrics and instance invocation admission | ui_button_contract.py |
| Choice, checkbox, segments, progress, scrollbar and editable controls | ui_widgets.py |
| Scene labels/actions/icons; delegates material and pointer ownership | scene_components.py, ui_canvas_actions.py |
| Player adapter semantics; delegates action material | media_player_ui.py |
| Native context menu lifetime and palette | ui_context_menu.py |

Change semantic tones once in ui_theme.py, material geometry once in ui_chrome.py,
or metric variants once in ui_button_contract.py. Screens supply content/actions.
Do not capture THEME values in default arguments: resolve them at construction.
Callbacks, focus, selected values and transient state remain instance-owned.

Motifs: Violet smoke; Cobalt/Ember paint splatter; Jade/Rose cherry blossoms;
Custom accent smoke. assets/materials/manifest-v2.json identifies the three original grayscale
artworks and their hashes. The original strip atlas is retained as earlier evidence. All tabs enroll via shared frame adapters; Library/Watch also enroll
their actual scene canvases. Fixed 1200x800 full-composition rasters move on configure without
resampling. The bounded pixel LRU holds at most eight theme combinations. Motifs remain low frequency and readable beneath continuous noninteractive content.
Opaque per-label or metadata rectangles are rejected; real media is never recolored.

Approved brand masters and ICNS remain unchanged. App-only brand derivatives
preserve dimensions, source alpha/geometry and luminance texture while taking
theme tones, including the wordmark and branded placeholders. The custom color
is a hue seed: stored preference stays exact; visible roles use normalized matte
tones to preserve contrast. Status labels/checkmarks/error messages carry meaning;
success/warning/error must not depend on color distinction.

Exceptions are explicit: system file pickers and macOS native menu geometry remain
OS-owned; video letterboxing remains black; source media and thumbnails retain
their original colors. These are not alternate app styling systems. No universal
native/platform/package acceptance follows from the scoped constructor audit.

Validation includes source contrast and hue checks, rejected import-time palette
defaults and private face-clone negative controls, all-theme tab/settings/native
control galleries, settings persistence, appearance event observation, actual-pixel
shared primary perturbation, existing metric propagation and temporal suites.
A settled screenshot must first verify the transition cover has retired. Inspect
complete scenes and controls at native scale; palette checks alone do not certify
the design. See the harness guide for evidence limits.

### Composition and material refinement

The initial faint heading strips and line-band bevels did not meet the visual
direction. Smoke, botanical blossoms and gestural pigment now have distinct full
compositions, a quiet left region and faded image edges. Their maximum tint
contribution is 28%; tests check muted text against each rendered artwork's
brightest channel bound, not just the plain palette.

ui_chrome owns Gaussian inner light/occlusion and diffuse cast shadows. Stretch
zones are normalized for Tk nine-slice tiling. The enclosing Forge panel was
rejected. Shared background enrollment projects the same artwork coordinates
through nested frame surfaces, with one shared theme image per top-level window.
This does not introduce a container, input handler, selection or callback owner.
Composite URL editing uses CanvasFieldMaterial, which owns only paint/focus.

FactsText measures whether a path fits the value column. A short path remains
inline; a longer path moves below its label and retains value-column alignment.
A slash alone is not a reason to force a line break.


### Revised foreground and composition direction

The user reference separates matte surfaces from colored content. Material faces,
backgrounds and artwork remain monochrome per theme. Foreground roles action,
icon, selection, progress, success, warning and danger provide limited intentional
color; ordinary text remains neutral. Status also requires words or symbols.
Do not enforce one hue over every rendered pixel or recolor actual media. Shared
owners consume these roles; no screen-local palette copies.

Plain rectangular backing behind noninteractive labels, status and metadata is
not accepted. Frame underlays alone do not solve opaque leaf widgets. Acceptance
requires actual native captures across empty, active, completed and error states,
with resize/theme seam and stale-backing checks. Preserve native text selection
and accessibility. This documented requirement is not a claim that all adapters
currently meet it. Retain failed captures and distinguish the isolated qualified
Tk runtime from stock and packaged runtime results.


### Smooth etched stone material

The authoritative reference is a continuous smooth matte stone-like substrate.
Each theme chooses one material hue shared by the background, artwork, control
faces, cards and popups. Recesses are carved into that same material; raised
controls emerge gently from it. Geometry stays crisp and directional light and
ambient occlusion supply depth. Avoid separate plastic-looking plates and rough
granite wallpaper. Background artwork is a restrained tonal surface treatment.
Selective colored foreground glyphs and indicators read as inlays; ordinary text
remains neutral. Verify actual per-theme rendered scene/control hue relationships,
not token existence alone, plus full scene switches and the interaction gates.


### Native read-only text over scene artwork

MatteTextProjection in ui_materials owns presentation over existing read-only
Text and Label widgets. Their documents, variables, geometry, selection and
keyboard bindings remain native; a nonfocusable child canvas paints aligned
artwork and text using native font geometry. Pointer coordinates are forwarded
to the document, and variable/modification/theme/geometry invalidation is scoped
to the owner. Destruction retires pending paint, traces and bindings. It does not
enroll editable fields or change data/selection models. Forge and Activity use this shared adapter. Native viewport notifications keep
scrollbars, keyboard movement and see() synchronized; visible display-row bounds
avoid scanning hidden wide-line tails. Embedded document images and status labels
retain their native owners, and elided tokens remain selectable without being painted.
This is not complete app-wide adoption or accessibility qualification. Direct
NSAccessibility inspection of the isolated Tk content view exposed AXUnknown and
no children both before and after projection; external assistive-technology behavior
is still unproven.

The source-native regression uses an independent two-tone background to amplify
seams, inserts a real opaque rectangle as a negative control, and checks native
selection, resizes and teardown. A prior hide-overlay control failed to produce
a visible fault on the tested Tk runtime; that failed evidence is retained.
Add active/completed/error states, theme changes, long documents and keyboard/
accessibility/performance checks when extending this owner. Keep physical-pixel
captures and their backing-scale metadata alongside logical previews.


Controls must stand alone on the shared substrate. Audit residual wrapper fills,
rectangular raster halos, duplicate borders and idle highlights across all control
families, screens and popups. Preserve meaningful keyboard focus, shaped to the
control, and distinguish idle/hover/mouse-focus/keyboard-focus/pressed/disabled
and focus exit. Patterned backgrounds expose unwanted rectangular support; check
pixels outside the intentional shaped material/shadow, not only control centers.
No blanket translucent overlay substitutes for removing a redundant wrapper.


### Intentional foreground roles

| Meaning | Shared role | Usage |
| --- | --- | --- |
| Ordinary content | text / muted | Neutral titles, labels and supporting information |
| Interactive action | action / icon | Same cyan for primary action labels and interactive glyphs |
| Selected or in progress | selection / progress | Same lavender for selected indicators and progress fills |
| Successful outcome | success | Green, paired with completion text or a check |
| Warning | warning | Amber, paired with warning text/icon |
| Failure or destructive meaning | danger | Rose, paired with explicit words/icon |
| Unavailable | subtle | Disabled foreground, with native disabled semantics |

These roles are shared across views and themes. Aliases have equal values by
contract, not arbitrary near-matching colors. Material tint, focus material and
foreground status are separate meanings. Do not assign colors by screen or by
control family, and do not color every label. New consumers must use the canonical
role and extend actual rendered state propagation tests.

### Field raster ownership

`RoundedFieldBorder` and the `Product.field` ttk element share `field_border_image`; the canvas uses a full backing and ttk uses its existing nine-slice backing. The logical sizes and native entry/choice editing owners remain unchanged. `platform_services.create_surface_image` can update an existing image: macOS uses its named native surface adapter to replace an NSImage representation under the same Tcl image name, while the 1x PhotoImage fallback pastes same-size state changes. The Mac adapter obtains native display scale before the first NSWindow is mapped, preventing permanently installed low-density ttk slices. No bitmap cache or per-screen style authority is added. Field inset depth is half-strength to retain the smooth matte surface without a harsh black top edge. Foreground/focus roles remain palette-owned. Native-density and fallback evidence are intentionally separate; other controls and Windows logical scaling are not implied qualified by field results.


### State-outline audit, v83 baseline (historical findings; current disposition below)

Coop identified residual focus and active-pill borders. Native current captures
confirm the selected SegmentedSelector perimeter ring. The shared material's
normal crisp contour is not the extra state outline being removed. Hover,
selection and focus must remain distinct; no underline or unreviewed marker is
an approved replacement. A review-only macOS prototype renders deeper existing
inset material and text contrast; product code still retains current focus.

| Existing owner / consumers | Finding | Status / required check |
| --- | --- | --- |
| ui_chrome._matte_rim; ttk_surface_image | Explicit THEME focus perimeter ring feeds button, field, checkbox, segment and transport images | Confirmed producer; current segment native capture. Review inset-only focus including selected+focused before adoption. |
| navigation_button_image; top/sidebar/navigation aliases | Independent rounded focus rectangle; selected idle already uses concavity | Confirmed producer. Current and proposed actual focused/selected/unfocused/hover captures available. |
| draw_scene_focus_ring; CanvasActions, LibraryScene, Watch and SceneRail | Full target polygon; CanvasActions also draws it for pointer press | Confirmed source paths. Pointer press is separate from keyboard focus and should rely on existing pressed material. Native consumer proof pending. |
| SegmentedSelector | Focus ring through material; selected fill and semantic text already separate | All ordinary/compact/separated focused native before captures retained. No proposed replacement accepted yet. |
| ProductEntry, ChoiceDropdown, PillAction, LibrarySearchField | Shared field focus ring; dropdown treats open popover as focused | Actual field prototype captured; open-menu and search consumer checks pending. Search also has fixed neutral outer frame contour, not a state change. |
| ChoiceMenu / ChoicePopover | Selected row uses recessed surface; popover has zero native highlight | Source inspected; no added selected perimeter seen. Native current popup/theme confirmation pending. |
| RunHoverMenu | Selected row still uses flat surface_2 fill | Legacy state surface; separate native confirmation/adoption pending. |
| Archive.TNotebook.Tab / inspector | Retains native Notebook.focus element | Confirmed active inspector constructor; native focus/selected capture pending. |
| EditableTextCard and collection Listbox | Native highlightcolor accent borders (1px/2px) | Confirmed reachable edit/list constructors. Preserve edit caret/selection and list keyboard orientation during replacement. |
| Player volume slider | Extra oval around focused knob | Source confirmed; native player focus and interaction proof pending. |
| ActivityModeSlider | Face glyph outlines are semantic artwork; focus changes thumb value contrast | Not classified as a full-control state outline. Actual focused mode capture pending. |
| FocusDestination/FocusIcon/CloudDisabled style aliases | Legacy maps remain, but no constructors found referencing these exact aliases | Dormant candidates, not live-consumer proof; do not count source matches as observed UI. |
| Consent illustrations / archive folder silhouettes / neutral dialog frames | Accent outlines draw artwork or fixed boundaries | Excluded from state-outline defect unless actual interaction changes them. |

Evidence: build/ui-foundation-20260917/state-borders-v83-before and
state-borders-v83-proposal (in the canonical vodforge evidence checkout).
Prototype is runtime monkeypatching inside an evidence-only test; no shared
producer/consumer repair has been applied. All previous DPI and release gates
remain unchanged.


v85-v86 follow-up: reviewed inset-only treatment is now integrated in shared
matte/ttk/navigation producers with semantic focus_surface, and inspector tabs
reuse the same selected/focus images. Actual Tab/Shift-Tab across five preset
themes restores selected nav, entry and segment pixels/content; notebook arrow
selection/restoration passes. Canvas pointer press uses pressed material alone.
The exception table remains open for scene keyboard targets, editor/listbox,
player volume and RunHoverMenu. No marker was introduced. Accessibility and
whole-app acceptance are not established solely by these captures or deltas.


### Current interaction material contract — v93

Coop's latest clarification is authoritative: resting, unpressed interactive
controls must look raised through shared light and shadow. Flat idle navigation
is superseded. Hovered, pressed and selected controls use the shared concave
material; keyboard focus remains visibly distinct through the semantic
focus_surface and inset shading. No underline, bright state perimeter or new
focus marker. Passive text and artwork remain passive. Foreground meaning is
unchanged; neutral material edges and icon outlines are not state borders.

Current repair scope:

- Shared matte/ttk/navigation focus uses material rather than a bright ring.
  Product/accent buttons retain native disabled/press behavior; focus takes
  precedence over hover. No-image segment fallback has no underline.
- Inspector tabs reuse the shared selected/focus images. Search/dropdown field
  interiors match focused material. Editor/list shells reuse RoundedFieldBorder;
  volume uses the existing field surface beneath its unchanged thumb.
- Canvas pointer press adds no extra polygon. Scene keyboard focus reuses the
  existing registered action base; artwork/card targets use transparent diffuse
  lighting. Registered actions never receive a second rim over a raised base.
- RunHoverMenu selected rows reuse navigation material. Native focus/selection,
  editing, dispatch and focus retirement are preserved in bounded checks.
- Interactive navigation now rests raised. Its images obey the existing ttk
  stretch contract: uniform center strips, preserved rounded corners and one
  face footprint across interaction states. v92's tiled grid is rejected and
  retained; v93 is the corrected representative rendering.

Evidence is macOS source-native: five preset-theme Tab/Shift-Tab cases; original
editor/list/volume failures then three passing input cases; full-app Library,
Watch and rail keyboard focus; 38 integrated material/DPI cases; a primary
focus+hover precedence case at default/injected192; and six real navigation
width/default-or-injected192 continuity/mutation cases. A final four-case actual
app navigation/scene run and76 source cases pass. The normal-size state sheet is
a derived1x review image; original captures remain unresampled native2x. Actual
OS physical DPI was not measured. These do not establish Windows, every consumer,
custom-theme extremes, physical-keyboard accessibility or packaged acceptance.
