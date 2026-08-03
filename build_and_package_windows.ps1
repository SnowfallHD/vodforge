# Builds and packages the runnable Windows app.
# Usage:
#   .\build_and_package_windows.ps1
#   .\build_and_package_windows.ps1 -Version "0.1.0"

param(
  [string]$Version = ""
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

& (Join-Path $PSScriptRoot "build_windows.ps1")

$distDir = Join-Path $PSScriptRoot "dist\VODForge"
if (-not (Test-Path $distDir)) {
  throw "Expected build output not found: $distDir"
}

$releaseDir = Join-Path $PSScriptRoot "dist\release"
New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null

$name = if ($Version) { "VODForge-Windows-v$Version.zip" } else { "VODForge-Windows.zip" }
$zip = Join-Path $releaseDir $name
Remove-Item $zip -Force -ErrorAction SilentlyContinue
Compress-Archive -Path $distDir -DestinationPath $zip -Force

Write-Host "Packaged runnable app: $zip"
