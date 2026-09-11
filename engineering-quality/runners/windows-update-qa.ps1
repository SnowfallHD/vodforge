param(
  [Parameter(Mandatory=$true)][string]$BaselineInstaller,
  [Parameter(Mandatory=$true)][string]$CandidateInstaller,
  [Parameter(Mandatory=$true)][string]$CandidateExecutable,
  [Parameter(Mandatory=$true)][string]$SourceRoot,
  [Parameter(Mandatory=$true)][string]$Python,
  [switch]$LegacyHandoff,
  [string]$OutputDirectory = 'E:\VODForgeQA\update-journeys'
)
# Run in an interactive Windows QA account. Never use a user's normal install.
$ErrorActionPreference = 'Stop'
$run = Join-Path $OutputDirectory ([guid]::NewGuid().ToString('N'))
$installRoot = Join-Path $run 'installed'
New-Item -ItemType Directory -Force $run | Out-Null
$receiptPath = Join-Path $run 'update-journey.json'
$result = @{ status='failed'; evidence_tier='windows-running-upgrade'; ui_click_verified=$false; source_commit=(& git -C $SourceRoot rev-parse HEAD) }
$old = $null
$new = $null
try {
  $env:VODFORGE_DISABLE_TELEMETRY = '1'
  $env:LOCALAPPDATA = Join-Path $run 'profile'
  $env:APPDATA = Join-Path $run 'roaming'
  $env:PYTHONPATH = $SourceRoot
  $env:PYINSTALLER_RESET_ENVIRONMENT = '1'
  foreach ($file in @($BaselineInstaller, $CandidateInstaller)) {
    $signature = Get-AuthenticodeSignature -LiteralPath $file
    if ($signature.Status -ne 'Valid' -or !$signature.TimeStamperCertificate -or !$signature.SignerCertificate.Subject.Contains('O="Kryden Ventures, LLC"')) { throw 'QA requires real signed installers' }
  }
  $setup = Start-Process $BaselineInstaller -ArgumentList @('/VERYSILENT','/NORESTART','/VODFORGEHANDOFF=1',('/DIR="'+$installRoot+'"')) -Wait -PassThru
  if ($setup.ExitCode -ne 0) { throw 'Baseline installation failed' }
  $exe = Join-Path $installRoot 'VODForge.exe'
  $baselineHash = (Get-FileHash $exe).Hash
  $candidateHash = (Get-FileHash $CandidateExecutable).Hash
  if ($baselineHash -eq $candidateHash) { throw 'Upgrade requires distinct baseline and candidate executables' }
  $old = Start-Process $exe -PassThru
  Start-Sleep -Seconds 4
  $old.Refresh()
  if ($old.HasExited -or $old.MainWindowHandle -eq 0) { throw 'Baseline app is not visibly running' }
  if ($LegacyHandoff) {
    # Match flags sent by already-installed older updaters. Inno's saved install
    # directory comes from the baseline installation in this isolated QA account.
    $setup = Start-Process $CandidateInstaller -ArgumentList @('/SP-','/SILENT','/CLOSEAPPLICATIONS','/RESTARTAPPLICATIONS') -PassThru
    if (!$setup.WaitForExit(900000)) { throw 'Legacy installer did not finish' }
    $setup.Refresh()
    if ($setup.ExitCode -ne 0) { throw ('Legacy installer failed: ' + $setup.ExitCode) }
    if (!$old.WaitForExit(10000)) { throw 'Legacy updater left the old process running' }
    Start-Sleep -Seconds 4
    $matches = @(Get-Process VODForge -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $exe -and $_.Id -ne $old.Id })
    if ($matches.Count -ne 1) { throw 'Legacy installer did not relaunch exactly one updated app' }
    $outcome = @{status='relaunched';pid=$matches[0].Id;installer_exit_code=0;executable_sha256=(Get-FileHash $exe).Hash;installed_version=(Get-Item $exe).VersionInfo.ProductVersion}
    $handoff = 'legacy installer flags'
  } else {
    # Production handoff owner while the baseline is still alive; UI callback is
    # covered separately, so this receipt does not claim an updater-button click.
    $handoff = & $Python -c 'from pathlib import Path; import sys; from yt_downloader.updates import launch_windows_update,verify_windows_authenticode; verify_windows_authenticode(Path(sys.argv[1])); print(launch_windows_update(Path(sys.argv[1]),executable=Path(sys.argv[2]),parent_pid=int(sys.argv[3])))' $CandidateInstaller $exe $old.Id
    if ($LASTEXITCODE -ne 0) { throw 'Production helper did not become ready' }
    if (!$old.CloseMainWindow()) { throw 'Baseline app refused graceful close' }
    if (!$old.WaitForExit(120000)) { throw 'Baseline did not exit; no force kill is allowed' }
    $deadline = (Get-Date).AddMinutes(16)
    while (!(Test-Path -LiteralPath $handoff) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500 }
    if (!(Test-Path -LiteralPath $handoff)) { throw 'No update outcome receipt' }
    $outcome = Get-Content -LiteralPath $handoff -Raw | ConvertFrom-Json
    if ($outcome.status -ne 'relaunched' -or $outcome.installer_exit_code -ne 0) { throw ('Update failed: ' + $outcome.error) }
  }
  $new = Get-Process -Id $outcome.pid -ErrorAction Stop
  $new.Refresh()
  if ($new.MainWindowHandle -eq 0 -or $new.Path -ne $exe) { throw 'Updated app is not visibly running from the expected target' }
  if ((Get-FileHash $exe).Hash -ne $candidateHash -or $outcome.executable_sha256 -ne $candidateHash) { throw 'Updated executable does not match candidate' }
  $result.status = 'passed'
  $result.legacy_handoff = [bool]$LegacyHandoff
  $result.baseline_sha256 = $baselineHash
  $result.candidate_sha256 = $candidateHash
  $result.installer_sha256 = (Get-FileHash $CandidateInstaller).Hash
  $result.installed_version = $outcome.installed_version
  $result.old_pid = $old.Id
  $result.new_pid = $new.Id
  $result.handoff_receipt = $handoff
} catch {
  $result.error = $_.Exception.Message
} finally {
  $result | ConvertTo-Json -Depth 6 | Set-Content $receiptPath -Encoding UTF8
  if ($new -and !$new.HasExited) { $null = $new.CloseMainWindow() }
  # Preserve all evidence and failed processes for inspection; never force kill.
}
if ($result.status -ne 'passed') { throw ('Update journey failed. See ' + $receiptPath) }
