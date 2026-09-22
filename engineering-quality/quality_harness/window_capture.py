"""Independent own-window pixel recorder for native diagnostic comparisons.

This process never drives input or calls into the application's widget runtime.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path


def main() -> int:
    import Quartz
    from PIL import Image

    parser = argparse.ArgumentParser()
    parser.add_argument("number", type=int)
    parser.add_argument("origin", type=float)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--interval", type=float, default=0.020)
    args = parser.parse_args()
    if not 0.020 <= args.interval <= 1:
        parser.error("capture interval must be between .020 and 1 second")
    number, origin, directory = args.number, args.origin, args.directory
    frames, errors = [], []
    deadline = time.monotonic() + 20
    try:
        while not (directory / "capture.stop").exists() and time.monotonic() < deadline:
            begin = time.monotonic() - origin
            raw = Quartz.CGWindowListCreateImage(
                Quartz.CGRectNull,
                Quartz.kCGWindowListOptionIncludingWindow,
                number,
                Quartz.kCGWindowImageBoundsIgnoreFraming
                | Quartz.kCGWindowImageNominalResolution,
            )
            if raw is None:
                raise RuntimeError("Own-window capture unavailable")
            data = bytes(
                Quartz.CGDataProviderCopyData(Quartz.CGImageGetDataProvider(raw))
            )
            bitmap = Image.frombytes(
                "RGB",
                (Quartz.CGImageGetWidth(raw), Quartz.CGImageGetHeight(raw)),
                data,
                "raw",
                "BGRX",
                Quartz.CGImageGetBytesPerRow(raw),
            )
            frames.append(
                {"begin": begin, "end": time.monotonic() - origin, "bitmap": bitmap}
            )
            if len(frames) == 1:
                (directory / "capture.ready").touch()
            time.sleep(max(0, args.interval - (time.monotonic() - origin - begin)))
        if not (directory / "capture.stop").exists():
            errors.append("Recorder deadline exceeded")
    except Exception as exc:  # noqa: BLE001 - retain unavailable evidence
        errors.append(repr(exc))
    for index, row in enumerate(frames):
        bitmap = row.pop("bitmap")
        name = f"resize-frame-{index:04d}.png"
        row.update(
            {
                "file": name,
                "size": list(bitmap.size),
                "sha256": hashlib.sha256(bitmap.tobytes()).hexdigest(),
            }
        )
        bitmap.save(directory / name, compress_level=0)
    (directory / "capture.json").write_text(
        json.dumps(
            {
                "frames": frames,
                "errors": errors,
                "requested_interval_seconds": args.interval,
                "observer": "separate process; shared window server; no application GIL",
            },
            indent=2,
        )
    )
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
