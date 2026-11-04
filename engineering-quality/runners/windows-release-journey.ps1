param(
  # Folder containing VODForge.exe (an extracted portable ZIP or an installed copy).
  [Parameter(Mandatory=$true)][string]$App,
  # Folder holding engineering-quality\ for this commit (see docs/release.md).
  [Parameter(Mandatory=$true)][string]$Source,
  [Parameter(Mandatory=$true)][ValidatePattern('^[A-Za-z0-9-]{4,64}$')][string]$JobId,
  [string]$Python = 'E:\VODForgeQA\tools\journey-venv\Scripts\python.exe',
  [int]$TimeoutMinutes = 30,
  [switch]$Worker
)
# Runs engineering-quality/runners/release_journey.py against a Windows build.
# UI Automation needs the logged-in desktop, so the journey runs as a task in
# the interactive session (never session 0). This script registers that task,
# waits for its result, prints it and removes the task again.
$ErrorActionPreference = 'Stop'
$run = Join-Path 'E:\VODForgeQA\runs' $JobId
$taskName = "VODForgeQA-journey-$JobId"
if (-not $Worker) {
  if (Test-Path $run) { throw "Refusing a reused run folder: $run" }
  if (-not (Test-Path (Join-Path $App 'VODForge.exe'))) { throw "VODForge.exe not found in $App" }
  New-Item -ItemType Directory -Path $run | Out-Null
  $user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
  $arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`" -App `"$App`" -Source `"$Source`" -JobId $JobId -Python `"$Python`" -Worker"
  $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments
  $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
  $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes $TimeoutMinutes)
  Register-ScheduledTask -TaskName $taskName -Action $action -Principal $principal -Settings $settings | Out-Null
  try {
    Start-ScheduledTask -TaskName $taskName
    $receipt = Join-Path $run 'receipt.json'
    $deadline = (Get-Date).AddMinutes($TimeoutMinutes + 2)
    while (-not (Test-Path $receipt) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 5 }
    if (Test-Path (Join-Path $run 'journey.log')) { Get-Content (Join-Path $run 'journey.log') }
    if (Test-Path $receipt) { Get-Content $receipt } else { throw 'The journey did not finish in time' }
  } finally {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
  }
  exit
}
$result = @{job_id = $JobId; passed = $false; session_id = [Diagnostics.Process]::GetCurrentProcess().SessionId}
try {
  if ($result.session_id -eq 0) { throw 'Not an interactive desktop session' }
  if (Get-Process LogonUI -ErrorAction SilentlyContinue | Where-Object SessionId -eq $result.session_id) { throw 'The desktop is locked' }
  $output = Join-Path $run 'journey'
  & $Python (Join-Path $Source 'engineering-quality\runners\release_journey.py') --app $App --output $output *> (Join-Path $run 'journey.log')
  $result.exit_code = $LASTEXITCODE
  $result.passed = $LASTEXITCODE -eq 0
  $result.result = Join-Path $output 'journey-result.json'
} catch {
  $result.error = $_.Exception.Message
} finally {
  $result | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $run 'receipt.json')
}
