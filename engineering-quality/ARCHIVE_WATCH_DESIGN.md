# Library and Watch design acceptance

Status: implementation and native verification in progress. This is the current
design direction for the source checkout, not an installed-build acceptance.
Passing source tests does not establish visual quality.

## Product intent

VODForge is a powerful, approachable media tool. The content leads: people should
understand where they are, what they can do next, and how to return without
learning an engineering interface. Restraint applies to the whole composition:
navigation, typography, spacing, artwork, empty states, and controls.

The five supplied professional examples inform craft, not copied features.
Generated VODForge references remain product composition references. Neither
mockups nor attractive individual controls establish implementation acceptance.

Use one principal action in a context. Keep secondary actions attached to their
subject and disclose them when useful. Hover actions must also be reachable by
keyboard. Technical facts belong in deliberate detail views. Counts, availability,
source facts, output results and recommendation membership remain truthful.

## Library

Browse through a quiet navigation column and a coherent content area. Artwork,
readable titles and a small amount of useful metadata establish hierarchy.
Search, sorting and selection have clear labels and defined shared control roles.
Selection tools appear when selection is requested.

An item detail page connects its artwork, title and actions with its description,
editable personal tags, and complete Source Details and Output Details.
Descriptions grow to a defined height and then scroll; copy returns full text.
Local description edits preserve provider metadata. One item-level vertical-dots
menu holds management actions; inline editing and copying stay with their content.

Facts use a stable value column, including continuation lines. Both source and
output include video and audio bitrates. Unknown measurements stay unknown;
requested encoding targets must not masquerade as measured output.
Exact paths remain copyable even when browse labels are shortened.

The retained folder workspace preserves ancestry, filters, grouped saved versions
and exact selection. Its folder subject must never inherit media actions.
Opening item details and returning must preserve the actual originating folder
context. Saved-version choices must belong to the current group and resolve
against current records. Full feature parity is a release requirement, including
notes, variant selection, source/output facts, file recovery and collection actions.

## Watch

The Watch home has a cinematic library-backed hero, followed by browsable content
sections. Recently Added, user collections, playlists and channels have clear
hierarchy. Collections sit between Recently Added and Playlists when present.
Rows scroll horizontally through every item with bounded rendering and retain
See All. Catalog views continue vertically without an arbitrary item cap.

Channel pages provide a visible, clearly labelled return action. Playlist pages
show their saved videos. A playlist with one video receives an intentional feature
layout rather than an almost-empty row or repeated placeholder cards.

Artwork is the play target. Play and Details are contextual and keyboard
accessible. Titles and durations must fit their actual rendered space.
Independent rows retain their own horizontal position and current action owners;
late artwork or replaced records cannot revive an obsolete action.

## Player and navigation

The normal player has a useful 16:9 viewport and defaults to Fit: preserve the
entire source picture and its aspect ratio. Letterboxing is valid. More to Watch
uses the right side when space permits and moves below at narrower widths.
Recently Added follows the player area.

Clicking the video toggles play/pause once. Transport controls share consistent
hover, focus, pressed and disabled states. Description, chapters, preview moments,
notes and tags, source and output information are expanded page content below
the player, with all existing capabilities preserved.

Top-level tab changes use a brief, subtle blur of the newly selected view.
Navigation within a tab is immediate. Release player resources before capturing
the new view; cancel obsolete timers, overlays and callbacks. No unrelated video
frame or thumbnail may flash during navigation. Optional appearance effects must
never block the requested action or navigation.

## Shared interaction requirements

Use the maintained components and behavior owners documented in
[the UI component catalog](../docs/ui-components.md), with architecture and
ownership in [the architecture guide](../docs/architecture.md). Thin adapters supply
content and scoped actions; they must not share unrelated mutable selection.

Scrolling is fractional and smooth, supports both axes, and routes nested input
once to the correct surface. A boundary can hand input to its parent without
double scrolling. Keyboard actions belong to the nearest active visible scope:
Escape closes the active popup only, or returns a detail/player view to its actual
origin. Enter saves a collection only in that active popup.

Collection creation uses a labelled Save button and the exact empty-field hint
“Type your collection name”. A visible focus treatment must not be confused with
selection or a scrollbar. All common control roles require intentional normal,
hover, focus, pressed and disabled states.

## Review and evidence

Review complete native compositions at 1440x900 and 1100x600 before zooming into
individual controls. Include populated facts, long titles and descriptions,
actual playback, one-video playlists, empty/search/loading/unavailable states,
selection, keyboard focus and resizing. Compare with the retained VODForge
references at ordinary viewing size.

Validate composed journeys, not only isolated widgets: folder filters to a saved
version to its correct facts and back; current-item context menus across reorder,
removal and modal dismissal; horizontal rows and See All within channel context;
late artwork after navigation; popup Enter/Escape; player teardown and tab changes.

Keep source checks, native input, packaged execution and physical-device claims
separate. OS-injected input is not physical input, a playback state is not proof
of audible sound, and a minimal-Tk comparison does not establish causality.
Preserve genuine failures and interrupted runs. Use the maintained
[quality workflow](README.md) and [release gate](RELEASE_GATE.md) to bind evidence
to the exact tested source and package.

The final private Mac replacement follows completion of the requested scope,
canonical documentation, native checks, backup and data verification. An
intermediate source checkpoint is not permission to present an incomplete build
as finished. Public deployment remains a separate authorization.
