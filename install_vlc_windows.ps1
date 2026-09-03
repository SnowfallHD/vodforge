# Downloads the pinned official VideoLAN libVLC runtime for offline playback.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$version = "3.0.23"
$expectedSha256 = "992d19dbd0b8a7cde9167d2f7780b1ef6f92acc8a71acfa736101a21f35181e1"
$url = "https://get.videolan.org/vlc/$version/win64/vlc-$version-win64.zip"
$archive = Join-Path $env:TEMP "vodforge-vlc-$version-win64.zip"
$extract = Join-Path $env:TEMP "vodforge-vlc-$version-win64"
$vendor = Join-Path $PSScriptRoot "vendor\vlc"

Write-Host "Downloading pinned libVLC $version from VideoLAN"
Invoke-WebRequest -Uri $url -OutFile $archive
$actualSha256 = (Get-FileHash -Path $archive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualSha256 -ne $expectedSha256) {
  throw "VideoLAN archive checksum mismatch: expected $expectedSha256, got $actualSha256"
}

Remove-Item -Recurse -Force $extract -ErrorAction SilentlyContinue
Expand-Archive -Path $archive -DestinationPath $extract -Force
$runtime = Get-ChildItem -Path $extract -Recurse -Filter "libvlc.dll" |
  Select-Object -First 1 |
  ForEach-Object { $_.Directory.FullName }
if (-not $runtime -or -not (Test-Path (Join-Path $runtime "libvlccore.dll")) -or -not (Test-Path (Join-Path $runtime "plugins"))) {
  throw "The official VideoLAN archive did not contain a complete libVLC runtime."
}

Remove-Item -Recurse -Force $vendor -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $vendor | Out-Null
Copy-Item (Join-Path $runtime "libvlc.dll") $vendor -Force
Copy-Item (Join-Path $runtime "libvlccore.dll") $vendor -Force
Copy-Item (Join-Path $runtime "plugins") (Join-Path $vendor "plugins") -Recurse -Force
Set-Content -Path (Join-Path $vendor "VODFORGE_VLC_VERSION") -Value $version -NoNewline
Write-Host "Installed verified libVLC $version to vendor\vlc"
