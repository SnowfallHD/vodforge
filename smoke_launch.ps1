$ErrorActionPreference = "Stop"
$exe = Join-Path $PSScriptRoot "dist\VODForge\VODForge.exe"
$p = Start-Process -FilePath $exe -PassThru
Start-Sleep -Seconds 5
if ($p.HasExited) {
  Write-Host "EXITED $($p.ExitCode)"
  exit 1
}
Write-Host "RUNNING pid=$($p.Id)"
Stop-Process -Id $p.Id -Force
Write-Host "STOPPED"
