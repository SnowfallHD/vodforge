param(
  [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{40}$')][string]$SourceCommit,
  [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{64}$')][string]$ArchiveSha256,
  [switch]$PreviewTelemetry
)
$ErrorActionPreference = 'Stop'
$root = 'E:\VODForgeQA'
$archive = Join-Path $root "artifacts\source-$SourceCommit.zip"
$source = Join-Path $root "sources\$SourceCommit"
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ArchiveSha256) {
  throw 'Source archive identity mismatch'
}
if (Test-Path -LiteralPath $source) { throw 'Source destination exists; refusing overwrite' }
New-Item -ItemType Directory -Path $source | Out-Null
Expand-Archive -LiteralPath $archive -DestinationPath $source
$env:VODFORGE_DISABLE_TELEMETRY = '1'
$env:VODFORGE_BUILD_TELEMETRY = 'disabled'
$env:VODFORGE_BUILD_VERSION = '0.1.8-dev'
if ($PreviewTelemetry) {
  $env:VODFORGE_BUILD_TELEMETRY = 'preview'
  $env:VODFORGE_BUILD_VERSION = '0.1.8'
}
$env:PIP_CACHE_DIR = Join-Path $root 'tools\pip-cache'
$env:PYINSTALLER_CONFIG_DIR = Join-Path $root 'tools\pyinstaller-cache'
$env:LOCALAPPDATA = Join-Path $root "profiles\build-$SourceCommit"
$env:TEMP = Join-Path $root 'tools\temp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
Set-Location $source
& .\install_ffmpeg_windows.ps1
& .\install_vlc_windows.ps1
& .\install_deno_windows.ps1
& .\build_windows.ps1
if (-not (Test-Path '.\dist\VODForge\VODForge.exe')) { throw 'Missing built executable' }
$receipt = @{
  source_commit=$SourceCommit
  source_archive_sha256=$ArchiveSha256
  executable=(Join-Path $source 'dist\VODForge\VODForge.exe')
  executable_sha256=(Get-FileHash '.\dist\VODForge\VODForge.exe' -Algorithm SHA256).Hash.ToLowerInvariant()
  telemetry_policy=$env:VODFORGE_BUILD_TELEMETRY
  app_version=$env:VODFORGE_BUILD_VERSION
  signed_release=$false
}
$receipt | ConvertTo-Json | Set-Content (Join-Path $root "artifacts\build-$SourceCommit.json")
$receipt | ConvertTo-Json -Compress
