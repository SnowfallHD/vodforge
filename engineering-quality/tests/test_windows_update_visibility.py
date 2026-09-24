"""The signed updater QA gate waits for the exact relaunched window."""

import shutil
import subprocess
from pathlib import Path

import pytest


def test_relaunched_window_waits_for_visibility_without_accepting_wrong_target():
    shell = shutil.which("pwsh") or shutil.which("powershell.exe")
    if shell is None:
        pytest.skip("PowerShell is required for the native Windows visibility gate")
    helper = (
        Path(__file__).resolve().parents[1]
        / "runners"
        / "windows-update-visibility.ps1"
    )
    script = f"""
. '{helper}'
$expected = 'E:\\QA\\VODForge.exe'
$script:tick = 0
$app = [pscustomobject]@{{ Path = $expected; MainWindowHandle = 0 }}
$app | Add-Member ScriptMethod Refresh {{ }}
$read = {{
  param($targetId)
  if ($targetId -ne 1234) {{ throw 'wrong PID requested' }}
  $script:tick += 1
  if ($script:tick -ge 3) {{ $app.MainWindowHandle = 456 }}
  return $app
}}
$now = {{ [datetime]'2026-01-01T00:00:00Z' + [timespan]::FromMilliseconds($script:tick * 250) }}
$pause = {{ param($milliseconds) }}
$ready = Wait-VODForgeUpdatedWindow -TargetProcessId 1234 -ExpectedPath $expected -TimeoutSeconds 2 -ReadProcess $read -Now $now -Pause $pause
if ($ready.MainWindowHandle -ne 456 -or $script:tick -ne 3) {{ throw 'delayed window was not accepted' }}
$app.Path = 'E:\\Other\\VODForge.exe'
$script:tick = 0
$app.MainWindowHandle = 456
try {{
  $null = Wait-VODForgeUpdatedWindow -TargetProcessId 1234 -ExpectedPath $expected -TimeoutSeconds 2 -ReadProcess $read -Now $now -Pause $pause
  throw 'wrong target was accepted'
}} catch {{
  if ($_.Exception.Message -ne 'Updated app is running from the wrong target') {{ throw }}
}}
$app.Path = $expected
$app.MainWindowHandle = 0
$script:tick = 0
$readNeverVisible = {{ param($targetId) $script:tick += 1; return $app }}
try {{
  $null = Wait-VODForgeUpdatedWindow -TargetProcessId 1234 -ExpectedPath $expected -TimeoutSeconds 1 -ReadProcess $readNeverVisible -Now $now -Pause $pause
  throw 'invisible window was accepted'
}} catch {{
  if ($_.Exception.Message -notlike '*within 1 seconds') {{ throw }}
}}
Write-Output 'WINDOW_VISIBILITY_CONTRACT_OK'
"""
    result = subprocess.run(
        [shell, "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "WINDOW_VISIBILITY_CONTRACT_OK" in result.stdout
