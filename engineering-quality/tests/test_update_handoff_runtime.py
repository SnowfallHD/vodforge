"""Execute the production Windows helper's control flow, with bounded OS doubles.

Windows-only, so skips on macOS must never count as Windows release proof.
"""

import os
import subprocess
import sys

import pytest

from yt_downloader.updates import windows_update_script


@pytest.mark.skipif(
    sys.platform != "win32" and not os.environ.get("VODFORGE_QA_POWERSHELL"),
    reason="requires PowerShell runtime",
)
@pytest.mark.parametrize(
    "outcome",
    [
        "success",
        "installer_failure",
        "wrong_version",
        "relaunch_failure",
        "parent_timeout",
        "invalid_signature",
        "repair_success",
        "repair_download_failure",
        "data_changed",
    ],
)
def test_windows_helper_runtime(tmp_path, outcome):
    receipt = tmp_path / "result.json"
    executable = tmp_path / "VODForge.exe"
    executable.touch()
    data = tmp_path / "saved-data"
    data.mkdir()
    saved = data / "download-history.json"
    saved.write_text('{"library": ["preserve me"]}')
    (data / "settings.json").write_text('{"telemetry": false}')
    media = tmp_path / "downloaded.mp4"
    media.write_bytes(b"existing media")
    script = windows_update_script(
        tmp_path / "VODForge-Windows-Setup-v1.2.3.exe",
        executable,
        123,
        receipt,
        tmp_path / "ready",
        data_dir=tmp_path / "saved-data",
    )
    # Suppress only presentation; execute the production failure and receipt flow.
    script = script.replace(
        '$choice = Show-VODForgeRecovery $stage ($result.error + "`r`nUpdate log: " + $receipt) $directory $backup',
        (
            "$choice = if (!$repairRequested) { 'repair' } else { 'later' }"
            if outcome.startswith("repair_")
            else "$choice = 'later'"
        ),
    )
    prefix = (
        r"""
function Get-Process { param($Id, $ErrorAction) $p=New-Object PSObject; $p | Add-Member ScriptMethod WaitForExit { param($ms) PARENT_EXIT }; return $p }
function Get-AuthenticodeSignature { return [pscustomobject]@{Status='SIGNATURE_STATUS'; TimeStamperCertificate='trusted'; SignerCertificate=[pscustomobject]@{Subject='CN="Kryden Ventures, LLC", O="Kryden Ventures, LLC"'}} }
function Get-Item { param($LiteralPath) if ($LiteralPath -like '*VODForge.exe') { return [pscustomobject]@{VersionInfo=[pscustomobject]@{ProductVersion='INSTALLED_VERSION'}} }; return Microsoft.PowerShell.Management\Get-Item -LiteralPath $LiteralPath }

function Start-Process {
 param($FilePath,$ArgumentList,[switch]$PassThru,$WorkingDirectory)
 $p=New-Object PSObject -Property @{Id=456;ExitCode=INSTALL_EXIT;HasExited=$true}
 $p | Add-Member ScriptMethod Refresh { }
 if ($FilePath -like '*Setup*') { $p | Add-Member ScriptMethod WaitForExit {param($ms) return $true} }
 else { $p | Add-Member ScriptMethod WaitForExit {param($ms) return APP_EXIT} }
 return $p
}
""".replace("PARENT_EXIT", "$false" if outcome == "parent_timeout" else "$true")
        .replace(
            "INSTALLED_VERSION", "0.1.8" if outcome == "wrong_version" else "1.2.3"
        )
        .replace("INSTALL_EXIT", "5" if outcome == "installer_failure" else "0")
        .replace("APP_EXIT", "$true" if outcome == "relaunch_failure" else "$false")
    )
    prefix = prefix.replace(
        "SIGNATURE_STATUS", "NotSigned" if outcome == "invalid_signature" else "Valid"
    )
    if outcome.startswith("repair_"):
        prefix = prefix.replace(
            "ExitCode=0", "ExitCode=$(if ($repairRequested) {0} else {5})"
        )
        override = (
            "function Get-VODForgeRepairInstaller { throw 'TEST: network unavailable' }\n"
            if outcome == "repair_download_failure"
            else "function Get-VODForgeRepairInstaller { return @{Path=$installer;Version='1.2.3'} }\n"
        )
        script = script.replace(
            "$ErrorActionPreference = 'Stop'",
            override + "$ErrorActionPreference = 'Stop'",
        )
    if outcome == "data_changed":
        prefix = prefix.replace(
            "$p=New-Object PSObject -Property",
            "Set-Content -LiteralPath (Join-Path $dataRoot 'download-history.json') -Value 'damaged'; $p=New-Object PSObject -Property",
        )
    path = tmp_path / "helper-test.ps1"
    path.write_text(prefix + script)
    result = subprocess.run(
        [
            os.environ.get("VODFORGE_QA_POWERSHELL", "powershell.exe"),
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
        # Reproduce an incompatible inherited module path from a parent shell.
        env={**os.environ, "PSModulePath": str(tmp_path / "foreign-modules")},
        timeout=30,
        **({"creationflags": 0x08000000} if sys.platform == "win32" else {}),
    )
    import json

    evidence = json.loads(receipt.read_text(encoding="utf-8-sig"))
    success = outcome in {"success", "repair_success"}
    assert (result.returncode == 0) == success, (result.stderr, evidence)
    assert evidence["status"] == ("relaunched" if success else "failed")
    assert media.read_bytes() == b"existing media"
    backup = tmp_path / "result.json.data-backup" / "download-history.json.backup"
    if outcome != "parent_timeout":
        assert backup.read_text() == '{"library": ["preserve me"]}'
    if outcome == "data_changed":
        assert evidence["stage"] == "checking_data", evidence
        assert "pid" not in evidence
    else:
        assert saved.read_text() == '{"library": ["preserve me"]}'
    if success:
        assert evidence["data_preserved_before_relaunch"] is True
    if not success:
        assert evidence["error"]
        assert "pid" not in evidence


@pytest.mark.skipif(sys.platform != "darwin", reason="requires macOS file tools")
@pytest.mark.parametrize(
    "outcome", ["success", "relaunch_failure", "signature_failure"]
)
def test_macos_swap_executes_relaunch_and_rollback(tmp_path, outcome):
    import plistlib
    import shlex

    from yt_downloader.updates import MacUpdatePlan, write_macos_swap_script

    staging = tmp_path / "staged-test"
    source = staging / "VODForge.app"
    target = tmp_path / "installed" / "VODForge.app"
    for app, marker in ((source, "new"), (target, "old")):
        (app / "Contents").mkdir(parents=True)
        (app / "marker").write_text(marker)
        (app / "Contents/Info.plist").write_bytes(
            plistlib.dumps({"CFBundleIdentifier": "com.snowfallhd.vodforge"})
        )
    opened = tmp_path / "opened"
    verifier = tmp_path / "verify"
    verifier.write_text(
        "#!/bin/bash\n"
        + (
            "exit 1\n"
            if outcome == "signature_failure"
            else "echo 'Identifier=com.snowfallhd.vodforge'\necho 'TeamIdentifier=76G5W4954G'\n"
        )
    )
    verifier.chmod(0o755)
    opener = tmp_path / "open"
    opener.write_text(
        '#!/bin/bash\nif [[ "$1" == --env ]]; then shift 2; fi\ncat "$1/marker" >> '
        + shlex.quote(str(opened))
        + "\n"
        + ("exit 1\n" if outcome == "relaunch_failure" else "exit 0\n")
    )
    opener.chmod(0o755)
    path = write_macos_swap_script(MacUpdatePlan(source, target, staging))
    script = (
        path.read_text()
        .replace("/usr/bin/codesign", shlex.quote(str(verifier)))
        .replace("/usr/bin/xcrun stapler", "/usr/bin/true")
        .replace("/usr/sbin/spctl", "/usr/bin/true")
        .replace("/usr/bin/open", shlex.quote(str(opener)))
        .replace("/usr/bin/logger", "/usr/bin/true")
    )
    path.write_text(script)
    result = subprocess.run(
        ["/bin/bash", str(path), "99999999", str(source), str(target), str(staging)],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert (result.returncode == 0) == (outcome == "success"), result.stderr
    assert (target / "marker").read_text() == ("new" if outcome == "success" else "old")
    assert (
        opened.read_text()
        == {"success": "new", "relaunch_failure": "newold", "signature_failure": "old"}[
            outcome
        ]
    )


@pytest.mark.skipif(
    sys.platform != "win32" and not os.environ.get("VODFORGE_QA_POWERSHELL"),
    reason="requires PowerShell runtime",
)
@pytest.mark.parametrize("outcome", ["closed", "refused", "timeout"])
def test_installer_closes_only_target_copy(tmp_path, outcome):
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2] / "scripts/windows_close_for_update.ps1"
    )
    marker = tmp_path / "closed.txt"
    prefix = (
        r"""
$global:marker = 'MARKER'
function Get-Process {
 param($Name,$ErrorAction)
 $target = [pscustomobject]@{Path='C:\QA\VODForge.exe'}
 $target | Add-Member ScriptMethod CloseMainWindow { Set-Content -LiteralPath $global:marker 'target'; return CLOSE_RESULT }
 $target | Add-Member ScriptMethod WaitForExit { param($ms) return WAIT_RESULT }
 $other = [pscustomobject]@{Path='C:\Other\VODForge.exe'}
 $other | Add-Member ScriptMethod CloseMainWindow { throw 'must not close another copy' }
 return @($target,$other)
}
""".replace("MARKER", str(marker).replace("'", "''"))
        .replace("CLOSE_RESULT", "$false" if outcome == "refused" else "$true")
        .replace("WAIT_RESULT", "$false" if outcome == "timeout" else "$true")
    )
    script = tmp_path / "close-test.ps1"
    script.write_text(
        prefix
        + "\n& {\n"
        + source.read_text()
        + "\n} -ExecutablePath 'C:\\QA\\VODForge.exe'\n"
    )
    result = subprocess.run(
        [
            os.environ.get("VODFORGE_QA_POWERSHELL", "powershell.exe"),
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        **({"creationflags": 0x08000000} if sys.platform == "win32" else {}),
    )
    assert (result.returncode == 0) == (outcome == "closed"), result.stderr
    assert marker.read_text(encoding="utf-8-sig").strip() == "target"


@pytest.mark.skipif(
    sys.platform != "win32" and not os.environ.get("VODFORGE_QA_POWERSHELL"),
    reason="requires PowerShell runtime",
)
@pytest.mark.parametrize("response_type", ["text", "bytes", "missing", "duplicate"])
def test_repair_parses_windows_checksum_response(tmp_path, response_type):
    from yt_downloader.windows_update_recovery import RECOVERY_FUNCTIONS

    # GitHub serves SHA256SUMS as an octet stream: Windows PowerShell returns byte[].
    # Stop at the network transport boundary after validating the release/checksum.
    functions = RECOVERY_FUNCTIONS.replace(
        "$request = [Net.HttpWebRequest]::Create($base + $name)",
        "throw 'VALIDATED_DOWNLOAD_REQUEST'",
    )
    checksum = "a" * 64 + "  VODForge-Windows-Setup-v1.2.3.exe"
    if response_type == "missing":
        checksum = "a" * 64 + "  unrelated.exe"
    if response_type == "duplicate":
        checksum += "`n" + checksum
    content = f'"{checksum}"'
    if response_type == "bytes":
        content = f"[Text.Encoding]::UTF8.GetBytes({content})"
    script = (
        functions
        + f"""
$ErrorActionPreference='Stop'
function Invoke-RestMethod {{ return @{{tag_name='v1.2.3';draft=$false;prerelease=$false;assets=@(@{{name='VODForge-Windows-Setup-v1.2.3.exe';size=10}})}} }}
function Invoke-WebRequest {{ return @{{Content={content}}} }}
try {{ Get-VODForgeRepairInstaller '{str(tmp_path).replace("'", "''")}' }}
catch {{ Write-Output $_.Exception.Message }}
"""
    )
    path = tmp_path / "checksum.ps1"
    path.write_text(script)
    result = subprocess.run(
        [
            os.environ.get("VODFORGE_QA_POWERSHELL", "powershell.exe"),
            "-NoProfile",
            "-File",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    expected = (
        "VALIDATED_DOWNLOAD_REQUEST"
        if response_type in {"text", "bytes"}
        else "The installer checksum could not be verified."
    )
    assert expected in result.stdout, result.stderr


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows Forms")
def test_windows_recovery_surface_owns_frame_and_centers_on_app(tmp_path):
    import json

    from yt_downloader.windows_update_recovery import RECOVERY_FUNCTIONS

    receipt = tmp_path / "layout.json"
    capture = r"""
    $whiteBorders = @()
    foreach ($height in @(405, 550)) {
        $form.ClientSize = New-Object Drawing.Size(620, $height)
        $bitmap = New-Object Drawing.Bitmap(620, $height)
        $form.DrawToBitmap($bitmap, (New-Object Drawing.Rectangle(0, 0, 620, $height)))
        $whiteBorders += ($bitmap.GetPixel(0, 0).ToArgb() -eq [Drawing.Color]::White.ToArgb() -and $bitmap.GetPixel(619, ($height-1)).ToArgb() -eq [Drawing.Color]::White.ToArgb() -and $bitmap.GetPixel(0, 200).ToArgb() -eq [Drawing.Color]::White.ToArgb() -and $bitmap.GetPixel(300, ($height-1)).ToArgb() -eq [Drawing.Color]::White.ToArgb())
        $bitmap.Dispose()
    }
    $form.ClientSize = New-Object Drawing.Size(620, 405)
    & $center
    $expectedX = $windowBounds[0] + $windowBounds[2] / 2
    $expectedY = $windowBounds[1] + $windowBounds[3] / 2
    @{white_borders=$whiteBorders;border=$form.FormBorderStyle.ToString();center_dx=($form.Left+$form.Width/2-$expectedX);center_dy=($form.Top+$form.Height/2-$expectedY);repair=$repair.Text;technical=$details.Text;buttons_inside=($repair.Bottom -lt $form.ClientSize.Height -and $download.Right -lt $form.ClientSize.Width)} | ConvertTo-Json | Set-Content -LiteralPath $layoutReceipt
"""
    script = RECOVERY_FUNCTIONS.replace("[void]$form.ShowDialog()", capture)
    script += f"""
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
$area=[Windows.Forms.Screen]::PrimaryScreen.WorkingArea
$windowBounds=@(($area.Left+40),($area.Top+40),([Math]::Min(1000,$area.Width-80)),([Math]::Min(720,$area.Height-80)))
$layoutReceipt='{str(receipt).replace("'", "''")}'
Show-VODForgeRecovery 'installing' 'test cause' 'C:\\VODForge' 'test backup'
"""
    path = tmp_path / "layout.ps1"
    path.write_text(script, encoding="utf-8-sig")
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-File", str(path)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        creationflags=0x08000000,
    )
    assert result.returncode == 0, result.stderr
    layout = json.loads(receipt.read_text(encoding="utf-8-sig"))
    assert layout["border"] == "None"
    assert layout["white_borders"] == [True, True]
    assert abs(layout["center_dx"]) <= 1
    assert abs(layout["center_dy"]) <= 1
    assert layout["buttons_inside"] is True
    assert layout["repair"] == "Repair VODForge"
    assert layout["technical"] == "Technical details"
