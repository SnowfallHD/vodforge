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
    ],
)
def test_windows_helper_runtime(tmp_path, outcome):
    receipt = tmp_path / "result.json"
    executable = tmp_path / "VODForge.exe"
    executable.touch()
    script = windows_update_script(
        tmp_path / "VODForge-Windows-Setup-v1.2.3.exe",
        executable,
        123,
        receipt,
        tmp_path / "ready",
    )
    # Prevent modal dialogs in fault cases; the durable error must still be written.
    script = script.replace(
        "Add-Type -AssemblyName System.Windows.Forms", "# no test dialog"
    )
    script = script.replace(
        "[System.Windows.Forms.MessageBox]::Show",
        "# [System.Windows.Forms.MessageBox]::Show",
    )
    prefix = (
        r"""
function Get-Process { param($Id, $ErrorAction) $p=New-Object PSObject; $p | Add-Member ScriptMethod WaitForExit { param($ms) PARENT_EXIT }; return $p }
function Get-AuthenticodeSignature { return [pscustomobject]@{Status='SIGNATURE_STATUS'; TimeStamperCertificate='trusted'; SignerCertificate=[pscustomobject]@{Subject='CN="Kryden Ventures, LLC", O="Kryden Ventures, LLC"'}} }
function Get-Item { param($LiteralPath) return [pscustomobject]@{VersionInfo=[pscustomobject]@{ProductVersion='INSTALLED_VERSION'}} }
function Get-FileHash { param($LiteralPath,$Algorithm) return [pscustomobject]@{Hash='test-hash'} }
function Start-Process {
 param($FilePath,$ArgumentList,[switch]$PassThru,$WorkingDirectory)
 $p=New-Object PSObject -Property @{Id=456;ExitCode=INSTALL_EXIT}
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
        timeout=30,
        **({"creationflags": 0x08000000} if sys.platform == "win32" else {}),
    )
    import json

    evidence = json.loads(receipt.read_text(encoding="utf-8-sig"))
    assert (result.returncode == 0) == (outcome == "success"), result.stderr
    assert evidence["status"] == ("relaunched" if outcome == "success" else "failed")
    if outcome != "success":
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
        '#!/bin/bash\ncat "$1/marker" >> '
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
