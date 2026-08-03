$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$vendorBin = Join-Path $PSScriptRoot "vendor\deno"
New-Item -ItemType Directory -Force -Path $vendorBin | Out-Null
$zip = Join-Path $vendorBin "deno.zip"
$url = "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip"

Write-Host "Downloading Deno JavaScript runtime from $url"
Invoke-WebRequest -Uri $url -OutFile $zip
Expand-Archive -Path $zip -DestinationPath $vendorBin -Force
Remove-Item $zip -Force

$deno = Join-Path $vendorBin "deno.exe"
if (-not (Test-Path $deno)) {
  throw "deno.exe was not found after extraction."
}
Write-Host "Installed: $deno"
