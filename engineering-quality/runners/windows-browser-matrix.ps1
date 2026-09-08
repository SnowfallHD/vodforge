$ErrorActionPreference = 'Stop'
$root = 'E:\VODForgeQA'
$env:npm_config_cache = Join-Path $root 'tools\npm-cache'
$env:TEMP = Join-Path $root 'tools\temp'
$env:TMP = $env:TEMP
& 'C:\Program Files\nodejs\npm.cmd' install --prefix (Join-Path $root 'tools') --ignore-scripts --no-audit --no-fund playwright@1.58.2
if ($LASTEXITCODE -ne 0) { throw 'Browser test dependency installation failed' }
Expand-Archive (Join-Path $root 'artifacts\site-client-current.zip') (Join-Path $root 'artifacts\site-client-current')
& 'C:\Program Files\nodejs\node.exe' (Join-Path $root 'tools\windows-browser-matrix.cjs') (Join-Path $root 'artifacts\site-client-current') (Join-Path $root 'artifacts\windows-browser-matrix.json') (Join-Path $root 'tools\analytics_browser_journey.js')
if ($LASTEXITCODE -ne 0) { throw 'Browser matrix failed; see receipt' }
