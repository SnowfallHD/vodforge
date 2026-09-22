"""Windows shell dialogs isolated from the application process."""

from __future__ import annotations

import json
import os
import subprocess  # nosec B404 - fixed PowerShell program and argv
from typing import Any

from .processes import hidden_window_subprocess_kwargs


def choose_windows_output_directory(
    initial_dir: str,
    *,
    runner: Any = subprocess.run,
) -> str | None:
    """Run the Windows shell folder picker out of process so shell failures cannot close VODForge."""
    command = (
        "$utf8=New-Object System.Text.UTF8Encoding($false);"
        "[Console]::OutputEncoding=$utf8;$OutputEncoding=$utf8;"
        "Add-Type -AssemblyName System.Windows.Forms;"
        "$dialog=New-Object System.Windows.Forms.FolderBrowserDialog;"
        "$dialog.Description='Choose where VODForge should save downloads.';"
        "$dialog.ShowNewFolderButton=$true;"
        "$initial=$env:VODFORGE_INITIAL_OUTPUT_DIR;"
        "if($initial -and (Test-Path -LiteralPath $initial -PathType Container)){$dialog.SelectedPath=$initial};"
        "if($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK){"
        "@{path=$dialog.SelectedPath} | ConvertTo-Json -Compress}"
    )
    environment = os.environ.copy()
    environment["VODFORGE_INITIAL_OUTPUT_DIR"] = initial_dir
    result = runner(
        ["powershell.exe", "-NoProfile", "-STA", "-Command", command],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        **hidden_window_subprocess_kwargs(),
    )
    if result.returncode:
        detail = str(result.stderr or "").strip()
        raise RuntimeError(detail or "Windows could not open the folder browser.")
    output = str(result.stdout or "").strip()
    if not output:
        return None
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Windows returned an unreadable folder selection.") from exc
    selected = payload.get("path") if isinstance(payload, dict) else None
    return str(selected) if selected else None
