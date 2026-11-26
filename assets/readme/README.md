# Public README screenshots

`current-design/mac/` and `current-design/windows/` hold the screenshots the
main README shows: the same seven screens (Forge, Library, Library item details,
Watch, the player, My Files, Issues & Recovery) on each platform. Each is an
unmodified window capture of the real app placed on a desktop wallpaper: macOS
with its own window shadow on the Catalina night wallpaper, Windows with a soft
added shadow on the Windows 10 default wallpaper. They show VODForge 0.3.0 with a
fictional sample library and telemetry off; no personal media or paths appear.
`current-design/manifest.json` records each file's hash, platform, app build and
capture date.

## Retaking them

1. Make the sample library with `scripts/seed_public_design_profile.py --home
   <new folder> --media <folder>`. On a Mac, put the media on a separate disk
   image (for example a sparse image named Media at `/Volumes/Media/VODForge`)
   so saved paths stay neutral; on Windows, map a drive letter with `subst M:`
   and use `M:\VODForge`. The script makes ten MP4s and two MP3s, a stopped run
   for Issues & Recovery, and settings that skip first-run prompts.
2. Launch the release app with `HOME` (Mac) or `LOCALAPPDATA` (Windows) set to
   that folder and `VODFORGE_DISABLE_TELEMETRY=1`.
3. Capture each screen at 1280×820:
   - **Mac:** `scripts/readme_screenshots/mac_ax.py PID size 1280 820 80 40`,
     then `press AXButton <name>` to navigate and `shot <file>.png shadow` to
     capture. For the player, `mac_hover.py PID X Y` over the video reveals its
     controls without moving the real pointer.
   - **Windows:** run `scripts/readme_screenshots/windows_capture.py` in the
     logged-in session; it clicks through every screen and saves the PNGs.
4. Frame each capture: `scripts/readme_screenshots/frame.py WALLPAPER WINDOW.png
   OUT.jpg --margin 0.07` (add `--shadow --width 1600` for Windows).
5. Check every image for personal paths, private media, clipping or stray
   prompts, then update `manifest.json`.

The wallpapers are not stored in this repository: the Catalina wallpaper is
Apple's and the Windows 10 wallpaper is Microsoft's. The website's press kit
carries the Windows one at `public/press/windows-desktop.jpg`.

`forge.png` and `library.png` in this folder are captures of the former Tk
interface (September 2026), kept only because older evidence records their
hashes.
