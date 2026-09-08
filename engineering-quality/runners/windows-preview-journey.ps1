param(
  [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{40}$')][string]$SourceCommit,
  [Parameter(Mandatory=$true)][string]$RunDirectory,
  [switch]$Extended
)
$ErrorActionPreference = 'Stop'
$root = 'E:\VODForgeQA'
$source = Join-Path $root "sources\$SourceCommit"
$build = Get-Content (Join-Path $root "artifacts\build-$SourceCommit.json") -Raw | ConvertFrom-Json
if ($build.telemetry_policy -ne 'preview') { throw 'Explicit preview build required' }
if (-not $RunDirectory.StartsWith("$root\runs\")) { throw 'Run must be in QA directory' }
$env:VODFORGE_QA_ACCESS_KEY = (Get-Content (Join-Path $root 'qa-access-key') -Raw).Trim()
if ($env:VODFORGE_QA_ACCESS_KEY -notmatch '^[a-f0-9]{64}$') { throw 'Missing QA credential' }
Remove-Item Env:VODFORGE_DISABLE_TELEMETRY -ErrorAction SilentlyContinue
$archive = Join-Path $RunDirectory 'portable.zip'
Compress-Archive -Path (Join-Path $source 'dist\VODForge') -DestinationPath $archive
Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $RunDirectory 'portable')
$receipts = @()
foreach ($kind in @('installed','portable')) {
  $exe = if ($kind -eq 'installed') { Join-Path $root 'installed\VODForge\VODForge.exe' } else { Join-Path $RunDirectory 'portable\VODForge\VODForge.exe' }
  if ((Get-FileHash $exe -Algorithm SHA256).Hash.ToLowerInvariant() -ne $build.executable_sha256) { throw 'Wrong candidate' }
  $marker = Join-Path (Split-Path $exe) '_internal\VODFORGE_TELEMETRY_POLICY'
  if ((Get-Content $marker -Raw).Trim() -ne 'preview') { throw 'Wrong telemetry marker' }
  $cases = if ($Extended) { @(@('XX','allow'),@('US','allow')) } else { @(@('US','none'),@('DE','allow'),@('GB','deny'),@('XX','deny')) }
  foreach ($case in $cases) {
    $env:VODFORGE_QA_COUNTRY = $case[0]
    $env:VODFORGE_QA_PROFILE = Join-Path $RunDirectory "$kind-$($case[0])"
    $delay = if ($Extended -and $case[0] -eq 'XX') { 125 } else { 5 }
    $duration = if ($Extended -and $case[0] -eq 'XX') { 140 } else { 18 }
    if ($Extended -and $case[0] -eq 'US') {
      $env:HTTPS_PROXY = 'http://127.0.0.1:9'
      $env:HTTP_PROXY = $env:HTTPS_PROXY
    }
    $process = Start-Process $exe -ArgumentList @('--analytics-qa',$case[1],$delay,$duration) -PassThru
    if (-not $process.WaitForExit(170000)) {
      Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
      throw 'Owned preview app timed out'
    }
    $receipt = Get-Content (Join-Path $env:VODFORGE_QA_PROFILE 'startup-journey.json') -Raw | ConvertFrom-Json
    $opens = @($receipt.events | Where-Object kind -eq 'browser_requested')
    $prompts = @($receipt.events | Where-Object kind -eq 'permission_prompt_visible')
    if ($opens.Count -ne 1) { throw 'Expected exactly one welcome request' }
    if (-not $Extended -and (($case[0] -eq 'US') -eq ($prompts.Count -gt 0))) { throw 'Wrong permission prompt state' }
    if ($Extended -and $prompts.Count -ne 1) { throw 'Unknown region must ask permission' }
    if ($prompts.Count -gt 0) {
      $surface = @($receipt.events | Where-Object kind -eq 'permission_surface')
      if ($surface.Count -ne 1 -or -not $surface[0].centered -or $surface[0].native_backdrop_bands -ne 4) { throw 'Incomplete native consent presentation' }
    }
    if ($case[1] -ne 'none' -and @($receipt.events | Where-Object kind -eq 'permission_choice').Count -ne 1) { throw 'Consent choice was not exercised' }
    $receipts += @{kind=$kind;country=$case[0];journey=$receipt;executable_sha256=$build.executable_sha256}
    if ($Extended -and $case[0] -eq 'US') {
      Copy-Item (Join-Path $env:VODFORGE_QA_PROFILE 'startup-journey.json') (Join-Path $env:VODFORGE_QA_PROFILE 'offline-startup.json')
      Remove-Item Env:HTTPS_PROXY,Env:HTTP_PROXY
      $backoff = Get-Content (Join-Path $env:VODFORGE_QA_PROFILE 'telemetry-backoff.json') -Raw | ConvertFrom-Json
      $remaining = [Math]::Ceiling($backoff.until - [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()) + 1
      if ($remaining -gt 120) { throw 'Unexpectedly long offline retry backoff' }
      if ($remaining -gt 0) { Start-Sleep -Seconds $remaining }
      $process = Start-Process $exe -ArgumentList @('--analytics-qa','none','0','18') -PassThru
      if (-not $process.WaitForExit(45000)) { Stop-Process -Id $process.Id -Force; throw 'Offline recovery timed out' }
      $retry = Get-Content (Join-Path $env:VODFORGE_QA_PROFILE 'startup-journey.json') -Raw | ConvertFrom-Json
      if (@($retry.events | Where-Object kind -eq 'browser_requested').Count -ne 0) { throw 'Recovery reopened browser' }
      $state = Get-Content (Join-Path $env:VODFORGE_QA_PROFILE 'installation.json') -Raw | ConvertFrom-Json
      if (-not $state.first_launch_confirmed) { throw 'Recovery failed to deliver launch' }
    }
  }
}
$receipts | ConvertTo-Json -Depth 12 | Set-Content (Join-Path $RunDirectory 'preview-matrix.json')
