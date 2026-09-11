param([Parameter(Mandatory=$true)][string]$ExecutablePath)
# The signed installer extracts this script into its private temporary directory.
# Close only this installation using its normal shutdown handler; never force kill.
# Use this runtime's built-in modules even when launched under PowerShell 7.
$env:PSModulePath = $PSHOME + '/Modules'
$ErrorActionPreference = 'Stop'
try {
  $apps = @(Get-Process VODForge -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $ExecutablePath })
  foreach ($app in $apps) {
    if (!$app.CloseMainWindow()) { throw 'Close VODForge normally before installing.' }
    if (!$app.WaitForExit(120000)) { throw 'VODForge is still closing. Finish active work and retry.' }
  }
  exit 0
} catch {
  exit 1
}
