param([Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{32}$')][string]$JobId)
$ErrorActionPreference = 'Stop'
$run = Join-Path 'E:\VODForgeQA\runs' $JobId
$rows = @(Get-ChildItem $run -Directory | Where-Object Name -Match '^(installed|portable)-' | ForEach-Object {
  $state = Get-Content (Join-Path $_.FullName 'installation.json') -Raw | ConvertFrom-Json
  [pscustomobject]@{case=$_.Name;install_id=$state.install_id;launch=$state.first_launch_confirmed;claim=$state.attribution_claim_confirmed}
})
$rows | ConvertTo-Json
