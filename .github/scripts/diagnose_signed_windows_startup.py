"""Observe the same signed binary; no install, build, input synthesis or gate waiver."""
import ctypes
import hashlib
import json
import os
import subprocess
import sys
import time
import zipfile
from ctypes import wintypes
from pathlib import Path

import psutil

sys.path.insert(0, str(Path.cwd() / "engineering-quality"))
from quality_harness.windows_update_diagnostics import process_snapshot, window_snapshot

SOURCE = "26c141e356bd5bc6c4123b858ceb43bebc7bb6d8"
WRAPPER = "4e360cec678b958fea99c1e75ae7ffb7bade3402043580840aebc59b84bb5dac"
EXECUTABLE = "c4fe40abcb5384bf4459a87d511c8e5e6d26a421c80d336fadbfa5cc78126dc9"
archive, out = map(Path, sys.argv[1:])
out.mkdir()
assert hashlib.sha256(archive.read_bytes()).hexdigest() == WRAPPER
payload = out / "payload"
payload.mkdir()
with zipfile.ZipFile(archive) as z:
    names = z.namelist()
    assert names == ["VODForge-Windows-Portable-v0.2.3.zip", "VODForge-Windows-Setup-v0.2.3.exe"]
    portable = out / "portable.zip"
    portable.write_bytes(z.read(names[0]))
with zipfile.ZipFile(portable) as z:
    assert all(not Path(n).is_absolute() and ".." not in Path(n).parts for n in z.namelist())
    z.extractall(payload)
executables = list(payload.rglob("VODForge.exe"))
assert len(executables) == 1
exe = executables[0].resolve()
assert hashlib.sha256(exe.read_bytes()).hexdigest() == EXECUTABLE
for marker, expected in [("VODFORGE_BUILD_REVISION", SOURCE), ("VODFORGE_VERSION", "0.2.3"), ("VODFORGE_TELEMETRY_POLICY", "production")]:
    paths = list(exe.parent.rglob(marker))
    assert len(paths) == 1 and paths[0].read_text().strip() == expected
checkenv = dict(os.environ, DIAG_EXE=str(exe))
signature_script = out / "verify-signature.ps1"
signature_script.write_text("$env:PSModulePath = $PSHOME + '/Modules'\n$ErrorActionPreference='Stop'\ntry {\n$s=Get-AuthenticodeSignature -LiteralPath $env:DIAG_EXE\n$s | Select-Object Status,StatusMessage,@{n='SignerSubject';e={$_.SignerCertificate.Subject}},@{n='TimestampSubject';e={$_.TimeStamperCertificate.Subject}} | ConvertTo-Json\n& (Join-Path $env:GITHUB_WORKSPACE 'verify_windows_signatures.ps1') -Files $env:DIAG_EXE\nif (!$?) {throw 'Maintained signature verifier failed'}\nexit 0\n} catch {Write-Output $_;exit 1}\n", encoding="utf-8-sig")
signature = subprocess.run(["powershell", "-NoProfile", "-File", str(signature_script)], env=checkenv, capture_output=True)
(out / "signature.log").write_bytes(signature.stdout + signature.stderr)
assert signature.returncode == 0, "Maintained signature verification failed; inspect signature.log"
user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
results = []
for mode in ["direct", "production-shaped-hidden-helper"]:
    case = out / mode
    case.mkdir()
    profile = case / "profile"
    profile.mkdir()
    ready = case / "ready.json"
    env = dict(os.environ, HOME=str(profile), LOCALAPPDATA=str(profile), APPDATA=str(profile / "roaming"), VODFORGE_DISABLE_TELEMETRY="1", PYINSTALLER_RESET_ENVIRONMENT="1", DIAG_EXE=str(exe), DIAG_READY=str(ready), DIAG_PID=str(case / "pid.json"))
    assert env.get("QT_QPA_PLATFORM", "windows") != "offscreen"
    start = time.monotonic()
    if mode == "direct":
        process = subprocess.Popen([str(exe), "--ready-file", str(ready)], env=env, cwd=exe.parent)
        pid = process.pid
    else:
        helper = case / "helper.ps1"
        helper.write_text("$ErrorActionPreference='Stop'\n$p=Start-Process -FilePath $env:DIAG_EXE -ArgumentList @('--ready-file', ('\"'+$env:DIAG_READY+'\"')) -WorkingDirectory (Split-Path $env:DIAG_EXE) -PassThru\n@{pid=$p.Id}|ConvertTo-Json|Set-Content -LiteralPath $env:DIAG_PID\n", encoding="utf-8-sig")
        process = subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-File", str(helper)], env=env, creationflags=0x08000000)
        while not (case / "pid.json").exists() and time.monotonic() - start < 12:
            time.sleep(.1)
        pid = json.loads((case / "pid.json").read_text(encoding="utf-8-sig"))["pid"]
    first_visible = None
    first_ready = None
    samples = []
    row = {"mode": mode, "pid": pid, "candidate_source": SOURCE, "executable_sha256": EXECUTABLE, "original_visibility_guard_seconds": 30, "diagnostic_observation_limit_seconds": 120}
    while time.monotonic() - start < 120:
        elapsed = time.monotonic() - start
        processes, owners = process_snapshot(pid)
        windows = window_snapshot(owners)
        for window in windows:
            class_name = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(window["window_id"], class_name, len(class_name))
            window["class"] = class_name.value
        sample = {"elapsed_seconds": elapsed, "processes": processes, "windows": windows}
        if ready.exists():
            sample["ready"] = json.loads(ready.read_text())
            first_ready = elapsed if first_ready is None else first_ready
        if any(w.get("verified") and w.get("onscreen") and w.get("owner_pid") == pid for w in windows):
            first_visible = elapsed if first_visible is None else first_visible
        try:
            owner = psutil.Process(pid)
            assert Path(owner.exe()).resolve() == exe
            sample["cpu_times"] = list(owner.cpu_times())
            sample["threads"] = len(owner.threads())
            sample["module_basenames"] = sorted({Path(m.path).name for m in owner.memory_maps() if m.path})
        except psutil.Error as error:
            sample["process_inspection_error"] = type(error).__name__
        samples.append(sample)
        (case / "samples.json").write_text(json.dumps(samples, indent=2))
        if first_visible is not None and elapsed - first_visible >= 3:
            break
        if not psutil.pid_exists(pid):
            break
        time.sleep(2)
    row.update(first_ready_seconds=first_ready, first_native_visible_seconds=first_visible, strict30_visibility_observed=first_visible is not None and first_visible <= 30)
    if ready.exists():
        row["ready_checkpoint"] = json.loads(ready.read_text())
    # Close only this verified owned window through the normal WM_CLOSE path.
    if psutil.pid_exists(pid):
        assert Path(psutil.Process(pid).exe()).resolve() == exe
        for w in samples[-1]["windows"]:
            if w.get("owner_pid") == pid and w.get("title", "").startswith("VODForge"):
                user32.PostMessageW(w["window_id"], 0x0010, 0, 0)
        deadline = time.monotonic() + 15
        while psutil.pid_exists(pid) and time.monotonic() < deadline:
            time.sleep(.2)
    row["owned_pid_survives_normal_close"] = psutil.pid_exists(pid)
    results.append(row)
    (out / "diagnostic-receipt.json").write_text(json.dumps({"kind": "same-signed-artifact startup diagnosis; original failed gate unchanged", "source": SOURCE, "wrapper_sha256": WRAPPER, "cases": results, "publication": False, "product_changes": False}, indent=2))
    print(json.dumps(row), flush=True)
    if row["owned_pid_survives_normal_close"]:
        break  # Never force kill or launch another app beside a stuck owned app.
