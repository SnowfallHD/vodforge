function Wait-VODForgeUpdatedWindow {
  param(
    [Parameter(Mandatory=$true)][int]$TargetProcessId,
    [Parameter(Mandatory=$true)][string]$ExpectedPath,
    [int]$TimeoutSeconds = 30,
    [scriptblock]$ReadProcess = { param($targetId) Get-Process -Id $targetId -ErrorAction Stop },
    [scriptblock]$Now = { Get-Date },
    [scriptblock]$Pause = { param($milliseconds) Start-Sleep -Milliseconds $milliseconds }
  )
  if ($TimeoutSeconds -le 0) { throw 'Updated-app visibility timeout must be positive' }
  $deadline = (& $Now).AddSeconds($TimeoutSeconds)
  while ($true) {
    $candidate = & $ReadProcess $TargetProcessId
    if (!$candidate) { throw 'Updated app exited before its window appeared' }
    $candidate.Refresh()
    if ($candidate.Path -and $candidate.Path -ne $ExpectedPath) {
      throw 'Updated app is running from the wrong target'
    }
    if ($candidate.MainWindowHandle -ne 0 -and $candidate.Path -eq $ExpectedPath) {
      return $candidate
    }
    if ((& $Now) -ge $deadline) {
      throw "Updated app did not show a window from the expected target within $TimeoutSeconds seconds"
    }
    & $Pause 250
  }
}
