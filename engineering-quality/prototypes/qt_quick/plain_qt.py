"""Native Qt window baseline for comparing corner drag transport only."""

import argparse
import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickWindow


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ready-file", type=Path, required=True)
    parser.add_argument("--event-log", type=Path)
    args = parser.parse_args()
    application = QGuiApplication(sys.argv[:1])
    window = QQuickWindow()
    window.setTitle("VODForge Qt Quick prototype baseline")
    window.setX(30)
    window.setY(30)
    window.setWidth(1100)
    window.setHeight(740)
    window.setMinimumWidth(820)
    window.setMinimumHeight(560)
    window.show()

    def record_ready() -> None:
        args.ready_file.write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "window_id": int(window.winId()),
                    "visible": window.isVisible(),
                    "geometry": [
                        window.x(),
                        window.y(),
                        window.width(),
                        window.height(),
                    ],
                }
            )
        )

    QTimer.singleShot(300, record_ready)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
