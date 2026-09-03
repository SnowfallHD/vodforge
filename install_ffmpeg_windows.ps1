# Downloads a portable FFmpeg build with ffmpeg.exe, ffprobe.exe, and ffplay.exe.
# Run from PowerShell on Windows before build_windows.ps1 if you want a fully bundled app.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$vendor = Join-Path $PSScriptRoot "vendor\ffmpeg"
$tmp = Join-Path $env:TEMP "ffmpeg-release-essentials.zip"
$url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

New-Item -ItemType Directory -Force -Path $vendor | Out-Null
Write-Host "Downloading FFmpeg from $url"
Invoke-WebRequest -Uri $url -OutFile $tmp

$extract = Join-Path $env:TEMP "ffmpeg-release-essentials"
Remove-Item -Recurse -Force $extract -ErrorAction SilentlyContinue
Expand-Archive -Path $tmp -DestinationPath $extract -Force

$bin = Get-ChildItem -Path $extract -Recurse -Filter "ffmpeg.exe" | Select-Object -First 1 | ForEach-Object { $_.Directory.FullName }
if (-not $bin) { throw "Could not find ffmpeg.exe in downloaded archive." }

Remove-Item -Recurse -Force $vendor -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path (Join-Path $vendor "bin") | Out-Null
Copy-Item (Join-Path $bin "ffmpeg.exe") (Join-Path $vendor "bin\ffmpeg.exe") -Force
Copy-Item (Join-Path $bin "ffprobe.exe") (Join-Path $vendor "bin\ffprobe.exe") -Force
Copy-Item (Join-Path $bin "ffplay.exe") (Join-Path $vendor "bin\ffplay.exe") -Force

Write-Host "Installed portable FFmpeg to vendor\ffmpeg\bin"
