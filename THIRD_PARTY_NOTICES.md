# Third-party runtime notices

VODForge bundles third-party components for downloading, media conversion, and
local playback. Downloading online media requires an internet connection; local
conversion and playback can work offline.

VODForge's own source is covered by [the MIT license](LICENSE). The components
below retain their own copyrights and licenses. This document identifies the
principal runtimes and supporting libraries; it is not a complete inventory of
every library linked into a platform binary or a replacement for their license
texts and corresponding-source requirements.

## yt-dlp

VODForge uses yt-dlp to extract YouTube metadata and download media. The pinned
Python package for VODForge 0.1.9 is yt-dlp 2026.08.19. yt-dlp's own source is
dedicated to the public domain under the Unlicense; its dependencies and bundled
third-party code retain their separate licenses.

- Project and source: https://github.com/yt-dlp/yt-dlp
- License: https://github.com/yt-dlp/yt-dlp/blob/master/LICENSE
- Third-party licenses: https://github.com/yt-dlp/yt-dlp/blob/master/THIRD_PARTY_LICENSES.txt

### yt-dlp-ejs

The yt-dlp-ejs JavaScript solver resources support YouTube extraction. The package
combines Unlicense, MIT, and ISC licensed code, including its third-party
JavaScript dependencies.

- Project and source: https://github.com/yt-dlp/ejs
- License: https://github.com/yt-dlp/ejs/blob/main/LICENSE
- Bundled JavaScript licenses: https://github.com/yt-dlp/ejs#licensing

## FFmpeg / ffprobe

VODForge invokes FFmpeg for media conversion and packaging, and ffprobe for media
inspection and output validation. FFmpeg's base license is LGPL 2.1 or later,
but enabling optional GPL components changes the license of the resulting build.
The Homebrew macOS build used for 0.1.9 enables GPL and version-3 components and
reports GPL 3.0 or later. The Windows release-essentials builds supplied by
Gyan Doshi are GPL 3.0 builds. These distributions must not be described as
LGPL-only. Included codec libraries retain their applicable notices as well.

- Project: https://ffmpeg.org/
- Source and releases: https://ffmpeg.org/download.html
- License and distribution guidance: https://ffmpeg.org/legal.html
- GPL 3.0 license text: https://www.gnu.org/licenses/gpl-3.0.html
- macOS build recipe and dependencies: https://formulae.brew.sh/formula/ffmpeg
- Windows build provider, configuration, and source links: https://www.gyan.dev/ffmpeg/builds/

The exact binary's `ffmpeg -version`, `ffmpeg -buildconf`, and `ffmpeg -L` output
identify its version, configuration, and effective license. Build-provider links
can change over time; they do not themselves constitute an archived copy of all
corresponding source for a VODForge release.

## Deno

VODForge bundles Deno to execute the JavaScript needed by yt-dlp's extraction
support. Deno is distributed under the MIT license. Its embedded third-party
components, including the JavaScript engine, have additional upstream notices.

- Project: https://deno.com/
- Source: https://github.com/denoland/deno
- License and third-party notices: https://github.com/denoland/deno/blob/main/LICENSE.md

## VideoLAN VLC / libVLC

The packaged internal player uses the official VideoLAN VLC 3.0.23 runtime through
LibVLC. VODForge does not use or display VLC's application interface. VLC is free
and open-source software distributed under several licenses. LibVLC and the core
playback modules are available under LGPL 2.1 or later; some optional modules in
the official runtime use GPL-compatible licenses.

- Project and source: https://www.videolan.org/vlc/
- Exact VLC source archive: https://download.videolan.org/pub/videolan/vlc/3.0.23/vlc-3.0.23.tar.xz
- License overview: https://www.videolan.org/legal.html
- LGPL playback-module announcement: https://www.videolan.org/press/lgpl.html

The VLC name and cone logo are trademarks of the VideoLAN non-profit
organization. VODForge is not affiliated with or endorsed by VideoLAN.

## python-vlc

The Python bindings are distributed under LGPL 2.1 or later.

- Project and source: https://github.com/oaubert/python-vlc

## Python, UI, and supporting libraries

Packaged builds also include Python and libraries needed by the application and
its download runtime. Platform and resolved dependency versions can differ.
Development-only test and analysis tools are not part of this runtime list.

| Component | Purpose | License / upstream information |
| --- | --- | --- |
| Python | Application runtime | [PSF license and included third-party notices](https://docs.python.org/3/license.html) |
| Tcl / Tk | Native desktop UI toolkit | [Tcl/Tk BSD-style licenses](https://www.tcl.tk/software/tcltk/license.html) |
| Pillow | Image loading and thumbnails | [MIT-CMU](https://github.com/python-pillow/Pillow/blob/main/LICENSE) |
| imageio-ffmpeg | FFmpeg discovery helper | [BSD 2-Clause](https://github.com/imageio/imageio-ffmpeg/blob/main/LICENSE) |
| PyObjC | macOS Cocoa integration | [MIT; upstream source and license files](https://github.com/ronaldoussoren/pyobjc) |
| Requests | HTTP transport | [Apache 2.0](https://github.com/psf/requests/blob/main/LICENSE) |
| urllib3 | HTTP connection support | [MIT](https://github.com/urllib3/urllib3/blob/main/LICENSE.txt) |
| certifi | Certificate trust bundle | [MPL 2.0](https://github.com/certifi/python-certifi/blob/master/LICENSE) |
| charset-normalizer | Text encoding detection | [MIT](https://github.com/jawah/charset_normalizer/blob/master/LICENSE) |
| idna | Internationalized domain names | [BSD 3-Clause](https://github.com/kjd/idna/blob/master/LICENSE.md) |
| websockets | WebSocket transport | [BSD 3-Clause](https://github.com/python-websockets/websockets/blob/main/LICENSE) |
| Brotli | HTTP content decompression | [MIT](https://github.com/google/brotli/blob/master/LICENSE) |
| PyCryptodomex | Cryptographic support for extraction | [BSD and public-domain portions](https://github.com/Legrandin/pycryptodome/blob/master/LICENSE.rst) |
| Mutagen | Audio metadata support | [GPL 2.0 or later](https://github.com/quodlibet/mutagen/blob/main/COPYING) |
| PyInstaller bootloader | Starts the packaged Python application | [GPL with the PyInstaller distribution exception](https://pyinstaller.org/en/stable/license.html) |

The PyInstaller exception permits distributing applications built with
PyInstaller under their own licenses; it does not change the licenses of other
bundled dependencies.

## Icons

- Lucide icons: ISC, with Feather-derived portions under MIT. The distributed
  notice is preserved in [assets/icons/lucide/LICENSE](assets/icons/lucide/LICENSE).
- Material icons: Apache 2.0. The distributed license is preserved in
  [assets/icons/lucide/MATERIAL_LICENSE](assets/icons/lucide/MATERIAL_LICENSE).

## Release scope

This expanded document was added to repository main after VODForge 0.1.9 was
published. Existing 0.1.9 download archives retain their original notices file;
changing this document does not modify those signed archives. Future builds
include this file through the existing macOS and Windows packaging scripts.
