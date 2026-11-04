param(
  # Checkout or archive of the commit under test, with .venv set up from
  # requirements-dev.txt and engineering-quality/requirements.txt.
  [Parameter(Mandatory=$true)][string]$Source,
  # Comma-separated test paths relative to $Source, as CI names them.
  [Parameter(Mandatory=$true)][string]$Tests,
  [string]$RunRoot = 'E:\VODForgeQA\runs\devtest'
)
# Runs pytest on the Windows test PC the way CI does (offscreen, software Qt),
# to reproduce a Windows-only failure. Temporary files go under $RunRoot. The
# tests' conftest keeps the app out of the real profile; this script also checks
# that the account's real VODForge folder is byte-for-byte unchanged afterwards
# (see "Tests must not reach the real user's profile" in ../README.md).
$ErrorActionPreference = 'Stop'
Set-Location $Source
$env:QT_QUICK_BACKEND = 'software'
$env:QT_QUICK_CONTROLS_STYLE = 'Basic'
$env:VODFORGE_DISABLE_TELEMETRY = '1'
$env:TEMP = Join-Path $RunRoot 'tmp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force $env:TEMP | Out-Null

function ProfileHash {
  $folder = Join-Path $env:LOCALAPPDATA 'VODForge'
  if (-not (Test-Path $folder)) { return '' }
  Get-ChildItem $folder -Recurse -File | Sort-Object FullName |
    ForEach-Object { "$($_.FullName) $((Get-FileHash $_.FullName).Hash)" } | Out-String
}

$before = ProfileHash
$log = Join-Path $RunRoot 'pytest.log'
$list = ($Tests -split ',') -join ' '
cmd /c ".venv\Scripts\python.exe -m pytest -q --tb=short -p no:cacheprovider $list > `"$log`" 2>&1"
$code = $LASTEXITCODE
Get-Content $log | Select-String -Pattern '^(FAILED|ERROR|E  |tests\\.*:\d+:|\d+ (passed|failed))' |
  Select-Object -First 120 | ForEach-Object { $_.Line }
if ((ProfileHash) -ne $before) {
  Write-Output 'REAL PROFILE CHANGED: restore it before anything else'
  exit 2
}
Write-Output 'real profile unchanged'
exit $code
