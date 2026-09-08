param(
  [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{40}$')][string]$SourceCommit,
  [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{32}$')][string]$JobId,
  [ValidateSet('native','playback','portable-playback','installed-playback','browser','app','preview','preview-extended','preview-visual')][string]$Suite = 'native',
  [switch]$Worker
)
$ErrorActionPreference = 'Stop'
$root = 'E:\VODForgeQA'
$source = Join-Path $root "sources\$SourceCommit"
$run = Join-Path $root "runs\$JobId"
$taskName = "VODForgeQA-$JobId"
if (-not $Worker) {
  if (Test-Path $run) { throw 'Refusing reused run identity' }
  New-Item -ItemType Directory -Path $run | Out-Null
  if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) { throw 'Task exists' }
  $user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
  $arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`" -SourceCommit $SourceCommit -JobId $JobId -Suite $Suite -Worker"
  $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments
  $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
  $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
  Register-ScheduledTask -TaskName $taskName -Action $action -Principal $principal -Settings $settings | Out-Null
  Start-ScheduledTask -TaskName $taskName
  @{task=$taskName;run=$run} | ConvertTo-Json -Compress
  exit
}
$result = @{job_id=$JobId;source_commit=$SourceCommit;passed=$false;session_id=[Diagnostics.Process]::GetCurrentProcess().SessionId}
try {
  if ($result.session_id -eq 0) { throw 'Not an interactive desktop session' }
  if (Get-Process LogonUI -ErrorAction SilentlyContinue | Where-Object SessionId -eq $result.session_id) { throw 'Desktop locked' }
  $env:VODFORGE_DISABLE_TELEMETRY = '1'
  $env:VODFORGE_NATIVE_UI_TESTS = '1'
  $env:PYTHONPATH = $source
  $env:TEMP = Join-Path $run 'temp'
  $env:TMP = $env:TEMP
  New-Item -ItemType Directory -Path $env:TEMP | Out-Null
  Set-Location $source
  if ($Suite -eq 'preview-visual') {
    $exe = Join-Path $root 'installed\VODForge\VODForge.exe'
    $build = Get-Content (Join-Path $root "artifacts\build-$SourceCommit.json") -Raw | ConvertFrom-Json
    $policy = Join-Path (Split-Path $exe) '_internal\VODFORGE_TELEMETRY_POLICY'
    if ($build.telemetry_policy -ne 'preview' -or (Get-Content $policy -Raw).Trim() -ne 'preview') { throw 'Not a preview candidate' }
    if ((Get-FileHash $exe -Algorithm SHA256).Hash.ToLowerInvariant() -ne $build.executable_sha256) { throw 'Candidate executable mismatch' }
    $result.executable_sha256 = $build.executable_sha256
    & .\.venv\Scripts\python.exe (Join-Path $root 'tools\windows-consent-visual.py') $exe $run *> (Join-Path $run 'visual.log')
    if ($LASTEXITCODE -ne 0) { throw 'Packaged consent visual capture failed' }
    $visual = Get-Content (Join-Path $run 'visual.json') -Raw | ConvertFrom-Json
    if (-not $visual.passed) { throw $visual.error }
    $result.passed = $true
  } elseif ($Suite -in @('preview','preview-extended')) {
    & (Join-Path $root 'tools\windows-preview-journey.ps1') -SourceCommit $SourceCommit -RunDirectory $run -Extended:($Suite -eq 'preview-extended')
    # PowerShell scripts signal failure by throwing; LASTEXITCODE belongs to
    # native executables and may be null/stale here.
    $matrix = Get-Content (Join-Path $run 'preview-matrix.json') -Raw | ConvertFrom-Json
    $expected = if ($Suite -eq 'preview-extended') {4} else {8}
    if (@($matrix).Count -ne $expected) { throw "Incomplete preview journey receipt: expected $expected, found $(@($matrix).Count)" }
    $result.passed = $true
  } elseif ($Suite -in @('playback','portable-playback','installed-playback')) {
    $env:LOCALAPPDATA = Join-Path $run 'local-app-data'
    & .\.venv\Scripts\python.exe scripts/generate_playback_fixtures.py --ffmpeg vendor/ffmpeg/bin/ffmpeg.exe --output (Join-Path $run 'fixtures') *> (Join-Path $run 'fixtures.log')
    if ($LASTEXITCODE -ne 0) { throw 'Fixture generation failed' }
    $exe = Join-Path $source 'dist\VODForge\VODForge.exe'
    if ($Suite -eq 'portable-playback') {
      $archive = Join-Path $run 'VODForge-portable.zip'
      Compress-Archive -Path (Join-Path $source 'dist\VODForge') -DestinationPath $archive
      Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $run 'extracted')
      $exe = Join-Path $run 'extracted\VODForge\VODForge.exe'
      $result.archive_sha256 = (Get-FileHash $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    if ($Suite -eq 'installed-playback') { $exe = Join-Path $root 'installed\VODForge\VODForge.exe' }
    $policy = Join-Path (Split-Path $exe) '_internal\VODFORGE_TELEMETRY_POLICY'
    if ((Get-Content $policy -Raw).Trim() -ne 'disabled') { throw 'Not a telemetry-disabled candidate' }
    $build = Get-Content (Join-Path $root "artifacts\build-$SourceCommit.json") -Raw | ConvertFrom-Json
    if ((Get-FileHash $exe -Algorithm SHA256).Hash.ToLowerInvariant() -ne $build.executable_sha256) { throw 'Candidate executable mismatch' }
    $env:VODFORGE_PLAYBACK_SMOKE_RECEIPT = Join-Path $run 'playback.json'
    $arguments = @('--playback-smoke') + @(Get-ChildItem (Join-Path $run 'fixtures') -File | Sort-Object Name | ForEach-Object { '"' + $_.FullName + '"' })
    $process = Start-Process $exe -ArgumentList $arguments -PassThru
    $result.pid = $process.Id
    $result.executable_sha256 = (Get-FileHash $exe -Algorithm SHA256).Hash.ToLowerInvariant()
    if (-not $process.WaitForExit(120000)) {
      Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
      throw 'Packaged playback timed out'
    }
    $result.exit_code = $process.ExitCode
    if ($process.ExitCode -ne 0) { throw 'Packaged playback failed' }
    $playback = Get-Content $env:VODFORGE_PLAYBACK_SMOKE_RECEIPT -Raw | ConvertFrom-Json
    if ($playback.success -ne $true) { throw 'Playback receipt did not pass' }
    $result.playback = $playback
    $result.passed = $true
  } elseif ($Suite -eq 'app') {
    & .\.venv\Scripts\python.exe (Join-Path $root 'tools\windows-app-probe.py') (Join-Path $root 'installed\VODForge\VODForge.exe') $run *> (Join-Path $run 'app.log')
    $result.exit_code = $LASTEXITCODE
    $result.passed = $LASTEXITCODE -eq 0
  } elseif ($Suite -eq 'browser') {
    & .\.venv\Scripts\python.exe (Join-Path $root 'tools\windows-browser-probe.py') (Join-Path $run 'browser.json') *> (Join-Path $run 'browser.log')
    $result.exit_code = $LASTEXITCODE
    $result.passed = $LASTEXITCODE -eq 0
  } else {
  & .\.venv\Scripts\python.exe -m pytest -q -s tests/test_analytics_native_journey.py tests/test_analytics_consent.py tests/test_analytics_startup.py tests/test_analytics_consent_ui.py tests/test_modal_backdrop.py *> (Join-Path $run 'tests.log')
  $result.exit_code = $LASTEXITCODE
  $result.passed = $LASTEXITCODE -eq 0
  }
} catch {
  $result.error = $_.Exception.Message
} finally {
  $result | ConvertTo-Json -Depth 12 | Set-Content (Join-Path $run 'receipt.json')
}
