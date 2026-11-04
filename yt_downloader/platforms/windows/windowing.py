from __future__ import annotations


def configure_app_identity() -> bool:
    import ctypes

    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(  # type: ignore[attr-defined]
        "SnowfallHD.VODForge"
    )
    return True
