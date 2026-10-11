"""VODForge application entry and non-GUI command dispatch."""

from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--channel-artwork-worker":
        from .channel_artwork_worker import main as artwork_main

        return artwork_main()
    if len(sys.argv) >= 3 and sys.argv[1] == "--debug-preflight":
        from .download_service import debug_preflight

        return debug_preflight(" ".join(sys.argv[2:]))
    from .qt_quick.main import main as qt_main

    return qt_main()


if __name__ == "__main__":
    raise SystemExit(main())
