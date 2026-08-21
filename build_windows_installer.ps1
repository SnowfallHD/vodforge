# Packages the built onedir application as a per-user Windows installer.
# Inno Setup keeps VODForge.exe and _internal together under LocalAppData so
# users never need to manage the runtime folder by hand.

param(
  [Parameter(Mandatory = $true)]
  [string]$Version
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if ($Version -notmatch '^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$') {
  throw "Version must use semantic versioning, for example 1.2.3."
}

$iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if (-not $iscc) {
  $standardPaths = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
  )
  $isccPath = $standardPaths | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
} else {
  $isccPath = $iscc.Source
}
if (-not $isccPath) {
  throw "Inno Setup 6 was not found. Install it or use -PortableOnly to create only the portable ZIP."
}

$appExe = Join-Path $PSScriptRoot "dist\VODForge\VODForge.exe"
if (-not (Test-Path $appExe)) {
  throw "Expected VODForge build not found: $appExe"
}

& $isccPath "/DMyAppVersion=$Version" (Join-Path $PSScriptRoot "installer_windows.iss")
if ($LASTEXITCODE -ne 0) {
  throw "Inno Setup failed with exit code $LASTEXITCODE."
}

Write-Host "Packaged per-user installer in dist\release."
