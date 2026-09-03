# Builds a Windows .exe for VODForge.
# Run from PowerShell on Windows:
#   .\build_windows.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw "Python was not found. Install Python 3.11+ from https://www.python.org/downloads/windows/ and check 'Add python.exe to PATH'."
}

python -m venv .venv
. .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt

$buildVersion = if ($env:VODFORGE_BUILD_VERSION) { $env:VODFORGE_BUILD_VERSION } else { "0.1.0-dev" }
if ($buildVersion -notmatch '^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$') {
  throw "VODFORGE_BUILD_VERSION must use semantic versioning, for example 1.2.3."
}
$buildMetadataDir = Join-Path $PSScriptRoot "build\version"
New-Item -ItemType Directory -Force -Path $buildMetadataDir | Out-Null
$buildVersionFile = Join-Path $buildMetadataDir "VODFORGE_VERSION"
Set-Content -Path $buildVersionFile -Value $buildVersion -NoNewline
$addData = @("--add-data", "$buildVersionFile;.")

$versionParts = $buildVersion.Split("-")[0].Split(".")
$numericVersion = "$($versionParts[0]), $($versionParts[1]), $($versionParts[2]), 0"
$displayVersion = $buildVersion.Replace("'", "''")
$versionResourceFile = Join-Path $buildMetadataDir "VODForge_version_info.txt"
$versionResource = @"
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=($numericVersion),
    prodvers=($numericVersion),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', 'Kryden Ventures, LLC'),
         StringStruct('FileDescription', 'VODForge'),
         StringStruct('FileVersion', '$displayVersion'),
         StringStruct('InternalName', 'VODForge'),
         StringStruct('LegalCopyright', 'Copyright (c) Kryden Ventures, LLC'),
         StringStruct('OriginalFilename', 'VODForge.exe'),
         StringStruct('ProductName', 'VODForge'),
         StringStruct('ProductVersion', '$displayVersion')]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"@
Set-Content -Path $versionResourceFile -Value $versionResource -Encoding UTF8
$versionFile = @("--version-file", $versionResourceFile)
$iconFile = Join-Path $PSScriptRoot "assets\VODForge.ico"
$iconPng = Join-Path $PSScriptRoot "assets\VODForge.png"
$iconAssetDir = Join-Path $PSScriptRoot "assets\icons\lucide"
if (-not (Test-Path $iconFile) -or -not (Test-Path $iconPng) -or -not (Test-Path $iconAssetDir)) {
  throw "VODForge icon assets are missing."
}
$iconArgs = @("--icon", $iconFile)
$addData += @("--add-data", "$iconFile;assets", "--add-data", "$iconPng;assets", "--add-data", "$iconAssetDir;assets/icons/lucide")
$addData += @("--add-data", "THIRD_PARTY_NOTICES.md;.")

# Bundle the transcode tools and the independently pinned libVLC playback runtime.
$addBinary = @()
$vendorBin = Join-Path $PSScriptRoot "vendor\ffmpeg\bin"
$ffmpeg = Join-Path $vendorBin "ffmpeg.exe"
$ffprobe = Join-Path $vendorBin "ffprobe.exe"
if (Test-Path $ffmpeg) {
  $addBinary += @("--add-binary", "$ffmpeg;.")
  Write-Host "Bundling ffmpeg.exe from $ffmpeg"
  if (Test-Path $ffprobe) {
    $addBinary += @("--add-binary", "$ffprobe;.")
    Write-Host "Bundling ffprobe.exe from $ffprobe"
  } else {
    throw "ffprobe.exe is required beside vendor ffmpeg.exe for a self-contained build."
  }
} else {
  throw "vendor\ffmpeg\bin must contain ffmpeg.exe and ffprobe.exe for a self-contained build."
}

$vlcRoot = Join-Path $PSScriptRoot "vendor\vlc"
$vlcLibrary = Join-Path $vlcRoot "libvlc.dll"
$vlcCore = Join-Path $vlcRoot "libvlccore.dll"
$vlcPlugins = Join-Path $vlcRoot "plugins"
$vlcVersionMarker = Join-Path $vlcRoot "VODFORGE_VLC_VERSION"
if (-not (Test-Path $vlcLibrary) -or -not (Test-Path $vlcCore) -or -not (Test-Path $vlcPlugins)) {
  throw "vendor\vlc must contain libvlc.dll, libvlccore.dll, and plugins. Run install_vlc_windows.ps1."
}
if (-not (Test-Path $vlcVersionMarker) -or (Get-Content $vlcVersionMarker -Raw).Trim() -ne "3.0.23") {
  throw "The Windows libVLC runtime must be pinned to 3.0.23. Run install_vlc_windows.ps1."
}
$addBinary += @("--add-binary", "$vlcLibrary;vlc")
$addBinary += @("--add-binary", "$vlcCore;vlc")
$addData += @("--add-data", "$vlcPlugins;vlc/plugins")
Write-Host "Bundling the pinned libVLC playback runtime from $vlcRoot"

$deno = Join-Path $PSScriptRoot "vendor\deno\deno.exe"
if (Test-Path $deno) {
  $addBinary += @("--add-binary", "$deno;.")
  Write-Host "Bundling deno.exe from $deno"
} else {
  Write-Host "WARNING: deno.exe missing; yt-dlp may warn that no JavaScript runtime is available. Run install_deno_windows.ps1 for best YouTube extraction support."
}

python -m PyInstaller `
  --noconfirm `
  --clean `
  --windowed `
  --name "VODForge" `
  --collect-all yt_dlp `
  @iconArgs `
  @versionFile `
  @addData `
  @addBinary `
  --hidden-import vlc `
  main.py

$appBinary = Join-Path $PSScriptRoot "dist\VODForge\VODForge.exe"
$smokeProcess = Start-Process -FilePath $appBinary -ArgumentList "--runtime-smoke" -Wait -PassThru
if ($smokeProcess.ExitCode -ne 0) {
  throw "Packaged VODForge runtime smoke failed with exit code $($smokeProcess.ExitCode)."
}

Write-Host "Built VODForge v$buildVersion`: dist\VODForge\VODForge.exe"
