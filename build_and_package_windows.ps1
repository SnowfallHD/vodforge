# Builds and packages the runnable Windows app.
# Usage:
#   .\build_and_package_windows.ps1
#   .\build_and_package_windows.ps1 -Version "0.1.0"

param(
  [string]$Version = "",
  [switch]$PortableOnly,
  [switch]$Sign
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$env:VODFORGE_BUILD_VERSION = if ($Version) { $Version } else { "0.1.0-dev" }
& (Join-Path $PSScriptRoot "build_windows.ps1")

$distDir = Join-Path $PSScriptRoot "dist\VODForge"
if (-not (Test-Path $distDir)) {
  throw "Expected build output not found: $distDir"
}

function Invoke-VODForgeTrustedSigning {
  param([Parameter(Mandatory = $true)][string[]]$Files)

  Import-Module TrustedSigning -ErrorAction Stop
  $params = @{
    Endpoint = "https://eus.codesigning.azure.net/"
    CodeSigningAccountName = "Kryden"
    CertificateProfileName = "kryden-public-signing"
    Files = ($Files -join ",")
    FileDigest = "SHA256"
    TimestampRfc3161 = "http://timestamp.acs.microsoft.com"
    TimestampDigest = "SHA256"
    Description = "VODForge"
    DescriptionUrl = "https://github.com/SnowfallHD/vodforge"
    ExcludeEnvironmentCredential = $true
    ExcludeWorkloadIdentityCredential = $true
    ExcludeManagedIdentityCredential = $true
    ExcludeSharedTokenCacheCredential = $true
    ExcludeVisualStudioCredential = $true
    ExcludeVisualStudioCodeCredential = $true
    ExcludeAzurePowerShellCredential = $true
    ExcludeAzureDeveloperCliCredential = $true
    ExcludeInteractiveBrowserCredential = $true
  }
  Invoke-TrustedSigning @params
  & (Join-Path $PSScriptRoot "verify_windows_signatures.ps1") -Files $Files
}

if ($Sign) {
  $applicationExe = Join-Path $distDir "VODForge.exe"
  Invoke-VODForgeTrustedSigning -Files @($applicationExe)
}

if (-not $PortableOnly) {
  & (Join-Path $PSScriptRoot "build_windows_installer.ps1") -Version $env:VODFORGE_BUILD_VERSION
  if ($Sign) {
    $installer = Join-Path $PSScriptRoot "dist\release\VODForge-Windows-Setup-v$($env:VODFORGE_BUILD_VERSION).exe"
    Invoke-VODForgeTrustedSigning -Files @($installer)
  }
}

$releaseDir = Join-Path $PSScriptRoot "dist\release"
New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null
$name = if ($Version) { "VODForge-Windows-Portable-v$Version.zip" } else { "VODForge-Windows-Portable.zip" }
$zip = Join-Path $releaseDir $name
Remove-Item $zip -Force -ErrorAction SilentlyContinue
Compress-Archive -Path $distDir -DestinationPath $zip -Force

Write-Host "Packaged portable app: $zip"
