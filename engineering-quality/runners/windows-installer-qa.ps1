param(
  [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{40}$')][string]$SourceCommit
)
$ErrorActionPreference = 'Stop'
$root = 'E:\VODForgeQA'
$source = Join-Path $root "sources\$SourceCommit"
$compiler = Join-Path $root 'tools\InnoSetup\ISCC.exe'
if (-not (Test-Path $compiler)) {
  $download = Join-Path $root 'tools\innosetup-6.7.3.exe'
  Invoke-WebRequest 'https://github.com/jrsoftware/issrc/releases/download/is-6_7_3/innosetup-6.7.3.exe' -OutFile $download -UseBasicParsing
  $signature = Get-AuthenticodeSignature $download
  if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'CN=Pyrsys B\.V\.') {
    throw 'Inno Setup publisher signature invalid'
  }
  $setup = Start-Process $download -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/NOICONS',"/DIR=$root\tools\InnoSetup") -Wait -PassThru
  if ($setup.ExitCode -ne 0) { throw 'Compiler setup failed' }
}
$env:PATH = (Split-Path $compiler) + ';' + $env:PATH
$env:VODFORGE_DISABLE_TELEMETRY = '1'
$env:TEMP = Join-Path $root 'tools\temp'
$env:TMP = $env:TEMP
Set-Location $source
$build = Get-Content (Join-Path $root "artifacts\build-$SourceCommit.json") -Raw | ConvertFrom-Json
$version = if ($build.app_version) { $build.app_version } else { '0.1.8-dev' }
if ($build.telemetry_policy -notin @('disabled','preview')) { throw 'Not an isolated candidate' }
& .\build_windows_installer.ps1 -Version $version
if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed' }
$installer = Join-Path $source "dist\release\VODForge-Windows-Setup-v$version.exe"
$installRoot = Join-Path $root 'installed\VODForge'
$setup = Start-Process $installer -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',"/DIR=$installRoot") -Wait -PassThru
if ($setup.ExitCode -ne 0) { throw 'VODForge installer failed' }
$installed = Join-Path $installRoot 'VODForge.exe'
$expected = (Get-FileHash (Join-Path $source 'dist\VODForge\VODForge.exe')).Hash
if ((Get-FileHash $installed).Hash -ne $expected) { throw 'Installed executable mismatch' }
@{source_commit=$SourceCommit;installed=$installed;executable_sha256=$expected;installer_sha256=(Get-FileHash $installer).Hash;telemetry=$build.telemetry_policy;release=$false} | ConvertTo-Json | Set-Content (Join-Path $root "artifacts\installer-$SourceCommit.json")
