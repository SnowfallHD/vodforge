param(
  [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{40}$')][string]$SourceCommit,
  [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{32}$')][string]$JobId,
  [switch]$Worker
)
$ErrorActionPreference = 'Stop'
$root = 'E:\VODForgeQA'
$run = Join-Path $root "runs\$JobId"
$source = Join-Path $root "sources\$SourceCommit"
if (-not $Worker) {
  if (Test-Path $run) { throw 'Refusing reused run identity' }
  New-Item -ItemType Directory $run | Out-Null
  $user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
  $arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`" -SourceCommit $SourceCommit -JobId $JobId -Worker"
  $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments
  $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
  $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
  Register-ScheduledTask -TaskName "VODForgeQA-$JobId" -Action $action -Principal $principal -Settings $settings | Out-Null
  Start-ScheduledTask -TaskName "VODForgeQA-$JobId"
  exit
}
$result = @{passed=$false; source_commit=$SourceCommit}
try {
  if ([Diagnostics.Process]::GetCurrentProcess().SessionId -eq 0) { throw 'Not interactive' }
  $build = Get-Content "$root\artifacts\build-$SourceCommit.json" -Raw | ConvertFrom-Json
  if ($build.telemetry_policy -ne 'preview') { throw 'Must use isolated preview package' }
  $archive = Join-Path $run 'portable.zip'
  Compress-Archive -Path "$source\dist\VODForge" -DestinationPath $archive
  Expand-Archive -LiteralPath $archive -DestinationPath "$run\portable"
  foreach ($kind in @('installed','portable')) {
    $exe = if ($kind -eq 'installed') { "$root\installed\VODForge\VODForge.exe" } else { "$run\portable\VODForge\VODForge.exe" }
    if ((Get-FileHash $exe).Hash.ToLowerInvariant() -ne $build.executable_sha256) { throw 'Candidate mismatch' }
    foreach ($mode in @('upgrade','fresh')) {
      $runnerArgs = @("$root\tools\packaged-migration.py",$exe,"$run\$kind-$mode","$root\qa-access-key")
      if ($mode -eq 'fresh') { $runnerArgs += '--fresh' }
      & "$source\.venv\Scripts\python.exe" @runnerArgs *> "$run\$kind-$mode.log"
      if ($LASTEXITCODE -ne 0) { throw "Failed $kind $mode" }
    }
  }
  $result.passed = $true
} catch { $result.error = $_.Exception.Message }
finally { $result | ConvertTo-Json | Set-Content "$run\receipt.json" }
