# Builds and packages the runnable Windows app.
# Usage:
#   .\build_and_package_windows.ps1
#   .\build_and_package_windows.ps1 -Version "0.1.0"

param(
  [string]$Version = "",
  [switch]$PortableOnly
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$env:VODFORGE_BUILD_VERSION = if ($Version) { $Version } else { "0.1.0-dev" }
& (Join-Path $PSScriptRoot "build_windows.ps1")

$distDir = Join-Path $PSScriptRoot "dist\VODForge"
if (-not (Test-Path $distDir)) {
  throw "Expected build output not found: $distDir"
}

$releaseDir = Join-Path $PSScriptRoot "dist\release"
New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null

$name = if ($Version) { "VODForge-Windows-Portable-v$Version.zip" } else { "VODForge-Windows-Portable.zip" }
$zip = Join-Path $releaseDir $name
Remove-Item $zip -Force -ErrorAction SilentlyContinue
Compress-Archive -Path $distDir -DestinationPath $zip -Force

Write-Host "Packaged portable app: $zip"

if (-not $PortableOnly) {
  & (Join-Path $PSScriptRoot "build_windows_installer.ps1") -Version $env:VODFORGE_BUILD_VERSION
}
