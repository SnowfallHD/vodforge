# Embedded playback backend evaluation

## Decision

VODForge uses libVLC 3.0.23 behind the provider-neutral `PlaybackBackend`
contract. The engine renders into a VODForge-owned native child surface while
VODForge retains its Tk controls, chapters, heatmap, previews, annotations, and
Library integration.

Live playback no longer uses FFmpeg raw RGB frames or a separate FFplay audio
process. libVLC owns decoding, audio output, video output, the shared clock,
seeking, volume, and hardware-decoder selection. FFmpeg remains a separate,
bounded owner for offline preview-thumbnail extraction only.

## Candidate findings

| Candidate | macOS embedding | Windows embedding | Packaging and maintenance | Result |
| --- | --- | --- | --- | --- |
| libVLC | A focused Cocoa bridge creates an `NSView` child inside the Tk player stage and passes it to `libvlc_media_player_set_nsobject`. | Tk exposes an `HWND` that libVLC accepts through `libvlc_media_player_set_hwnd`. | Official, checksummed 3.0.23 runtimes are available for both platforms. VODForge bundles the core and plugin runtime. | Selected. |
| libmpv | The ordinary `wid` path is not a supported macOS embedding contract. Both a raw Tk identifier and a bridged `NSView` pointer blocked the prototype. A reliable implementation would require the Render API plus an application-owned OpenGL/Metal context, update callbacks, swaps, and main-thread lifecycle. | Native window embedding is available, but it would leave macOS on a materially different and more complex renderer. | The Homebrew build links a broad dependency graph and is GPLv2+ by default. An LGPL build requires a custom `-Dgpl=false` build and a complete dependency-license audit. | Rejected for this architecture. |
| WebView / HTML5 video | Technically possible through WebKit. | Depends on WebView2 availability or bundling. | Adds browser/runtime and IPC lifecycles, platform codec differences, and focus/resize complexity despite libVLC meeting the native-child requirement. | Not advanced beyond fallback review. |

## Prototype evidence contract

The reusable packaged probe exercises the real backend and native surface
without constructing `DownloaderApp`:

1. load and play MP4;
2. pause and resume;
3. seek repeatedly near the beginning, middle, and end;
4. change volume without restarting playback;
5. resize the Tk-hosted native surface;
6. switch between files, including MP3;
7. destroy the active backend and surface;
8. create a new backend and reopen media; and
9. verify clean process exit.

The same probe is available to packaged artifacts through
`VODForge --playback-smoke <media> [...]`. Runtime smoke separately verifies
that the exact bundled libVLC instance can initialize. Normal application
errors remain isolated to the player and cannot mutate downloads or Library
state.

## Runtime and distribution boundary

- Windows uses the official VideoLAN 3.0.23 64-bit ZIP, pinned by SHA-256.
- macOS uses the official architecture-specific VideoLAN 3.0.23 DMG, pinned by
  SHA-256 and verified against VideoLAN's Apple signing team before its runtime
  is extracted.
- Release builds fail closed if another VLC version is supplied.
- VODForge disables libVLC metadata network access; local playback remains
  offline and does not fetch artwork or metadata.
- VODForge bundles third-party notices and exact upstream source/license links.
  The VLC runtime includes LGPL and GPL-compatible modules; distribution must
  retain those notices and corresponding-source availability. VODForge does not
  use the VLC application UI or trademarks as product branding.

## Ownership

- `playback_backend.py`: immutable contract and snapshots.
- `libvlc_backend.py`: single playback engine, clock, state, and native-provider
  lifecycle.
- `playback_surface.py`: HWND/NSView child-surface lifecycle and resize commits.
- `media_preview.py`: bounded FFmpeg preview extraction.
- `media_player_ui.py`: VODForge control rendering and user interaction only.
- `DownloaderApp`: resolve the selected Library item, construct the focused
  owners, and show the VODForge player surface.
