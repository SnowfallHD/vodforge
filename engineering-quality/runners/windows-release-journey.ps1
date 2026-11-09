param(
  # Folder containing VODForge.exe (an extracted portable ZIP), or with
  # -Installer, the folder to install the signed installer into for the test.
  [Parameter(Mandatory=$true)][string]$App,
  # Signed VODForge-Windows-Setup-v<version>.exe. The machine's own VODForge
  # uninstall entry and shortcuts are backed up first and restored afterwards.
  [string]$Installer = '',
  # Folder holding engineering-quality\ for this commit (see docs/release.md).
  [Parameter(Mandatory=$true)][string]$Source,
  [Parameter(Mandatory=$true)][ValidatePattern('^[A-Za-z0-9-]{4,64}$')][string]$JobId,
  [string]$Python = 'E:\VODForgeQA\tools\journey-venv\Scripts\python.exe',
  [int]$TimeoutMinutes = 30,
  # Which runner to drive the app with: the release journey or the deletion one.
  [ValidateSet('release_journey.py', 'deletion_journey.py', 'telemetry_delivery_journey.py')][string]$Journey = 'release_journey.py',
  # List the app's controls (types and names) instead of running the journey.
  [switch]$Inspect,
  [switch]$Worker
)
# Runs engineering-quality/runners/release_journey.py (or -Journey
# deletion_journey.py) against a Windows build.
#
# UI Automation needs the logged-in desktop, so the work runs as a task in the
# interactive session (never session 0). The task does everything, including
# the installer test and restoring the PC's registration, so a dropped SSH
# connection can't leave the machine half-changed. This script registers the
# task, waits for its receipt, prints it and removes the task.
$ErrorActionPreference = 'Stop'
$run = Join-Path 'E:\VODForgeQA\runs' $JobId
$taskName = "VODForgeQA-journey-$JobId"
$uninstallKey = 'HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\{2C217998-2315-41E3-99BA-3A0289331B54}_is1'
$shortcuts = @(
  (Join-Path ([Environment]::GetFolderPath('Programs')) 'VODForge.lnk'),
  (Join-Path ([Environment]::GetFolderPath('Desktop')) 'VODForge.lnk')
)
function Backup-Name($link) { (Split-Path $link -Leaf).Replace('.lnk', "-$(Split-Path (Split-Path $link) -Leaf).lnk") }

if (-not $Worker) {
  if (Test-Path $run) { throw "Refusing a reused run folder: $run" }
  if ($Installer) {
    if (Get-Process VODForge -ErrorAction SilentlyContinue) { throw 'Close VODForge before the installer test' }
    if ((Get-AuthenticodeSignature $Installer).Status -ne 'Valid') { throw 'The installer signature is not valid' }
    if (Test-Path $App) { throw "Refusing an existing install folder: $App" }
  } elseif (-not (Test-Path (Join-Path $App 'VODForge.exe'))) {
    throw "VODForge.exe not found in $App"
  }
  New-Item -ItemType Directory -Path $run | Out-Null
  $user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
  $arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`" -App `"$App`" -Source `"$Source`" -JobId $JobId -Python `"$Python`" -TimeoutMinutes $TimeoutMinutes -Journey $Journey"
  if ($Installer) { $arguments += " -Installer `"$Installer`"" }
  if ($Inspect) { $arguments += ' -Inspect' }
  $arguments += ' -Worker'
  $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments
  $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
  $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes ($TimeoutMinutes + 10))
  Register-ScheduledTask -TaskName $taskName -Action $action -Principal $principal -Settings $settings | Out-Null
  Start-ScheduledTask -TaskName $taskName
  $receipt = Join-Path $run 'receipt.json'
  $deadline = (Get-Date).AddMinutes($TimeoutMinutes + 12)
  while (-not (Test-Path $receipt) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 5 }
  if (Test-Path (Join-Path $run 'journey.log')) { Get-Content (Join-Path $run 'journey.log') }
  if (-not (Test-Path $receipt)) { throw "The journey did not finish in time; task $taskName is left to finish and restore" }
  Get-Content $receipt
  Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
  exit
}

$result = @{job_id = $JobId; passed = $false; session_id = [Diagnostics.Process]::GetCurrentProcess().SessionId}
$backup = Join-Path $run 'registration-backup'
try {
  if ($result.session_id -eq 0) { throw 'Not an interactive desktop session' }
  if (Get-Process LogonUI -ErrorAction SilentlyContinue | Where-Object SessionId -eq $result.session_id) { throw 'The desktop is locked' }
  if ($Installer) {
    New-Item -ItemType Directory -Path $backup | Out-Null
    cmd.exe /c "reg export `"$uninstallKey`" `"$backup\uninstall.reg`" /y >nul 2>&1"
    foreach ($link in $shortcuts) { if (Test-Path $link) { Copy-Item $link (Join-Path $backup (Backup-Name $link)) } }
    # Wait for the installer only: after a silent install it starts VODForge
    # (that is how in-app updates relaunch), and -Wait would wait on that too.
    $setup = Start-Process $Installer -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/DIR=$App") -PassThru
    $null = $setup.Handle
    $setup.WaitForExit()
    if ($setup.ExitCode -ne 0) { throw "Installer exited with $($setup.ExitCode)" }
    Start-Sleep -Seconds 3
    Get-Process VODForge -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$App\*" } | Stop-Process -Force
    if ((Get-AuthenticodeSignature (Join-Path $App 'VODForge.exe')).Status -ne 'Valid') { throw 'The installed VODForge.exe signature is not valid' }
    $result.installed = $App
  }
  $output = Join-Path $run 'journey'
  # Start-Process, not &: Windows PowerShell 5 turns a native program's stderr
  # into terminating errors under 'Stop' when redirected with *>.
  $arguments = @("`"$(Join-Path $Source "engineering-quality\runners\$Journey")`"", '--app', "`"$App`"", '--output', "`"$output`"")
  if ($Inspect) { $arguments += '--inspect' }
  # Wait for Python only, not for any app the journey launched.
  $runner = Start-Process $Python -ArgumentList $arguments -PassThru -NoNewWindow `
    -RedirectStandardOutput (Join-Path $run 'journey.log') -RedirectStandardError (Join-Path $run 'journey-stderr.log')
  $null = $runner.Handle  # Without this, ExitCode can read back empty.
  if (-not $runner.WaitForExit($TimeoutMinutes * 60 * 1000)) {
    Stop-Process -Id $runner.Id -Force
    throw "The journey did not finish within $TimeoutMinutes minutes"
  }
  $result.exit_code = $runner.ExitCode
  $result.passed = $runner.ExitCode -eq 0
  $result.result = $output
} catch {
  $result.error = $_.Exception.Message
} finally {
  if ($Installer -and (Test-Path $backup)) {
    # Each restore step runs on its own, so one failure can't skip the others.
    # Native tools go through cmd: Windows PowerShell 5 under 'Stop' turns any
    # stderr text (reg.exe reports success there) into a terminating error.
    $ErrorActionPreference = 'Continue'
    $restore = @()
    try { Get-Process VODForge -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$App\*" } | Stop-Process -Force } catch { $restore += "stop: $_" }
    cmd.exe /c "reg delete `"$uninstallKey`" /f >nul 2>&1"
    if (Test-Path "$backup\uninstall.reg") {
      cmd.exe /c "reg import `"$backup\uninstall.reg`" >nul 2>&1"
      if ($LASTEXITCODE -ne 0) { $restore += "registry import exit $LASTEXITCODE" }
    }
    foreach ($link in $shortcuts) {
      try {
        Remove-Item $link -Force -ErrorAction SilentlyContinue
        $saved = Join-Path $backup (Backup-Name $link)
        if (Test-Path $saved) {
          Copy-Item $saved $link -Force
          if ((Get-FileHash $saved).Hash -ne (Get-FileHash $link).Hash) { $restore += "shortcut differs: $link" }
        }
      } catch { $restore += "shortcut ${link}: $_" }
    }
    Start-Sleep -Seconds 2
    Remove-Item $App -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path $App) { $restore += "test install still present: $App" }
    $result.registration_restored = ($restore.Count -eq 0)
    $result.restore_problems = $restore
    if ($restore.Count -gt 0) { $result.passed = $false }
  }
  $result | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $run 'receipt.json')
}
