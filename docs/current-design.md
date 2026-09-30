# Current VODForge design

This guide describes the Qt Quick development interface. Public release 0.2.2
remains separate. The [UI component contract](ui-components.md) is normative for
new features; [architecture](architecture.md) identifies runtime owners. Historical
Tk evaluation, tuning and release evidence remains valid for its named artifact.

## Workspaces and navigation

| Place | What belongs here | Primary actions |
| --- | --- | --- |
| Forge | Composer, current/selected run, full friendly activity or technical log, output facts, Run Deck | Download/Queue, Options, Create video, run actions |
| Library | Saved video/audio, channels, playlists, collections, search and item details | Open item, organize, play, inspect files |
| Watch | Continue watching and saved-media discovery | Resume/Play, See All for a nonempty section |
| Activity | Recorded technical activity | Inspect, copy where offered |
| My Files | Physical folders and files at their real location | Browse, Back, Open this folder, select file |
| All media | Saved media independent of directory hierarchy | Select item, open details, play |
| Issues & Recovery | Interrupted attempts without an export and missing saved media | Locate, recover, retry with saved configuration |

Top navigation returns to its main screen. Back follows the recorded route that
opened details or the player. My Files Back returns through folder navigation.
Long breadcrumbs remain one line, with hidden ancestors in the shared popup.
Opening a folder replaces its listing; neighboring pane widths remain stable.
Catalogs scroll vertically without unused Previous/Next controls.

## Composition

Forge activity and output facts are equal-width peers separated by padding and a
fixed hairline. Keep the steps that actually happened after any terminal outcome;
never substitute only a final status or invent stages absent from the record.
Run cards retain identity, artwork and open menus while progress changes.
Watch also retains its featured item and rails during playback, while its progress
label and Resume/Play state follow the current saved playback position, including
replay and backwards seeks. Progress updates must not rebuild the browse page.

The folder inspector uses a large recognizable folder emblem without a frame,
centered with the folder label below. Selected media and thumbnails use artwork;
metadata uses a file emblem inside the recessed preview well. Open this folder
lives in the right inspector. A missing-media route opens the specific issue in
Issues & Recovery rather than duplicating recovery controls in My Files.

In recovery, group identity/status, source, retry settings and actions. Reuse Forge's
output choices and Custom component. Expanded choices stay directly under their
trigger. Retry remains in recovery with live preparing/downloading/conversion
state and clears only on success. Removing queued work is removal, not a stop.
Each empty Watch section owns its placeholders and disabled See All state.

## Controls and overlays

Use the shared owners in the [catalog](ui-components.md), including StoneButton,
StoneCheckBox, StonePopup, AnchoredPopup, InlineSelector and SceneIcon. Boolean
consent is a plain checkbox and label, never a checkbox on a raised button.
Actions use verb labels. Dropdown choices must open a real list, not cycle values.
Persistent inline choices expand beneath their trigger and collapse on a repeat
activation. Floating menus have one shared outer shadow, content-fitting height,
and captured trigger intent: a repeat click closes without immediate reopening.
The analytics prompt preserves its four violet emblems and single-line privacy
summaries in a shared responsive grid, with content-fitting height and visible
privacy and consent actions. Informational summaries are passive, not controls.

Support separates reply consent from optional deeper diagnostics. Diagnostics
remain explicit and default off; unavailable diagnostics explain their disabled
state. Input focus stays with an active editor. The X utility link opens only the
fixed public account URL, without media or installation context.

## Public screenshots and reproduction

Seven unmodified native app captures live in `assets/readme/current-design/`:
Forge, Library, Watch, player, Library details, My Files and Issues & Recovery.
The JSON manifest records source identity and hashes. Nature artwork is fictional
sample media; interface pixels are from the actual packaged Qt application.
ImageGen references guide website composition and are not public product captures.

`scripts/seed_public_design_profile.py` creates an isolated sample HOME using the
existing history/metadata formats. It refuses the normal HOME and existing targets.
It creates local playable nature fixtures and a fictional stopped run; it never
copies personal Library data. Launch the qualified Qt candidate with that HOME and
telemetry disabled, navigate the real app, and capture its window. Keep development
preview captions visible on the website and in the press kit until this design ships.

## Qualification

Review complete scenes at empty, single-item and populated states, minimum and
normal window widths, and keyboard/pointer interaction. Verify the changed journey
in the exact built app. Source tests, native packaged behavior, installed replacement
and public release are separate evidence tiers. New controls must pass the catalog's
whole-view checklist and bounded representative cross-owner invariants.

The website has a product narrative, three workspace tabs, My Files and recovery
stories, authoritative release download cards, FAQ and `/press/`. The press page
provides official logos, native screenshots, product overview, guidance and a ZIP.
Preserve existing download, attribution, consent and mobile handoff owners when
changing its presentation.
