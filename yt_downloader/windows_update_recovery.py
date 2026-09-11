"""Detached Windows recovery functions embedded in the verified updater helper."""

RECOVERY_FUNCTIONS = r"""
function Save-VODForgeData {
    param($DataRoot, $BackupRoot)
    $manifest = @{}
    if (!(Test-Path -LiteralPath $DataRoot)) { return $manifest }
    if ((Get-Item -LiteralPath $DataRoot).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Saved data uses a linked folder; automatic repair stopped.' }
    New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
    # Durable app state lives in root files. Logs and update downloads are not state.
    foreach ($file in Get-ChildItem -LiteralPath $DataRoot -File -Force) {
        if ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Saved data contains a link; automatic repair stopped before installation.' }
        $copy = Join-Path $BackupRoot ($file.Name + '.backup')
        Copy-Item -LiteralPath $file.FullName -Destination $copy -ErrorAction Stop
        $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
        if ((Get-FileHash -LiteralPath $copy -Algorithm SHA256).Hash -ne $hash) { throw 'The saved-data backup could not be verified.' }
        $manifest[$file.Name] = $hash
    }
    $manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $BackupRoot 'backup-manifest.json') -Encoding UTF8
    return $manifest
}
function Confirm-VODForgeData {
    param($DataRoot, $Manifest)
    foreach ($name in $Manifest.Keys) {
        $path = Join-Path $DataRoot $name
        if (!(Test-Path -LiteralPath $path -PathType Leaf) -or (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $Manifest[$name]) {
            throw 'Saved app data changed during installation. A backup was retained; automatic relaunch stopped to avoid overwriting it.'
        }
    }
}
function Get-VODForgeRepairInstaller {
    param($Destination)
    # Fixed official endpoints; never execute a URL supplied by an error or receipt.
    $root = 'https://github.com/SnowfallHD/vodforge/releases/download/'
    $release = Invoke-RestMethod -Uri 'https://api.github.com/repos/SnowfallHD/vodforge/releases/latest' -TimeoutSec 30
    if ($release.draft -or $release.prerelease -or $release.tag_name -notmatch '^v\d+\.\d+\.\d+$') { throw 'The latest stable release could not be identified.' }
    $name = 'VODForge-Windows-Setup-' + $release.tag_name + '.exe'
    $asset = @($release.assets | Where-Object { $_.name -eq $name })
    if ($asset.Count -ne 1 -or $asset[0].size -le 0 -or $asset[0].size -gt 4294967296) { throw 'The latest Windows installer is unavailable.' }
    $base = $root + $release.tag_name + '/'
    $checksums = (Invoke-WebRequest -UseBasicParsing -Uri ($base + 'SHA256SUMS.txt') -TimeoutSec 30).Content
    if ($checksums.Length -gt 2097152) { throw 'The release checksum file is too large.' }
    if ($checksums -is [byte[]]) { $checksums = [Text.Encoding]::UTF8.GetString($checksums) }
    $hashes = @($checksums -split "`n" | Where-Object { $_.Trim() -match ('^[a-fA-F0-9]{64}\s+\*?' + [regex]::Escape($name) + '$') })
    if ($hashes.Count -ne 1) { throw 'The installer checksum could not be verified.' }
    $expectedHash = ($hashes[0] -split '\s+')[0]
    $path = Join-Path $Destination $name
    $partial = $path + '.' + [guid]::NewGuid().ToString('N') + '.part'
    $response = $null; $inputStream = $null; $outputStream = $null
    try {
        $request = [Net.HttpWebRequest]::Create($base + $name)
        $request.Timeout = 30000
        $request.ReadWriteTimeout = 30000
        $response = $request.GetResponse()
        $inputStream = $response.GetResponseStream()
        $outputStream = [IO.File]::Create($partial)
        $buffer = New-Object byte[] 65536
        $total = 0
        while (($count = $inputStream.Read($buffer, 0, $buffer.Length)) -gt 0) {
            $total += $count
            if ($total -gt $asset[0].size) { throw 'The installer download exceeded its expected size.' }
            $outputStream.Write($buffer, 0, $count)
        }
        $outputStream.Dispose(); $outputStream = $null
        if ($total -ne $asset[0].size -or (Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash -ne $expectedHash) { throw 'The installer download could not be verified.' }
        Move-Item -LiteralPath $partial -Destination $path -Force
        return @{ Path = $path; Version = $release.tag_name.Substring(1) }
    } finally {
        if ($outputStream) { $outputStream.Dispose() }
        if ($inputStream) { $inputStream.Dispose() }
        if ($response) { $response.Dispose() }
        if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial }
    }
}
function Show-VODForgeRecovery {
    param($Stage, $Detail, $Directory, $Backup)
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $messages = @{
        waiting_for_exit = 'VODForge did not close in time. Close it normally, then select Repair VODForge.'
        backing_up = 'The saved-data backup could not be completed. Installation has stopped. Check that your drive has free space, then select Repair VODForge.'
        verifying = 'Windows could not verify this installer. Select Repair VODForge to download and verify a fresh signed copy. Do not run the rejected file.'
        verifying_install = 'The installer finished, but the expected VODForge version is missing from your app folder. Select Repair VODForge to reinstall in the correct folder.'
        installing = 'The installer did not finish installing the expected version. Close any open installer, then select Repair VODForge.'
        checking_data = 'Installation changed saved app data. A backup was retained. Select Open download page for help; do not uninstall VODForge or delete its saved data.'
        relaunching = 'The update installed, but VODForge could not reopen. Try opening VODForge from the Start menu. If it still will not open, select Repair VODForge.'
        downloading_repair = 'A fresh installer could not be downloaded or verified. Check your internet connection and try Repair VODForge again. If it still fails, select Open download page.'
    }
    $form = New-Object Windows.Forms.Form
    $form.Text = 'VODForge update needs attention'
    $form.ClientSize = New-Object Drawing.Size(620, 405)
    $form.StartPosition = 'Manual'
    $form.AutoScaleMode = 'None'
    $form.FormBorderStyle = 'None'
    $form.BackColor = [Drawing.ColorTranslator]::FromHtml('#08090a')
    $form.ForeColor = [Drawing.ColorTranslator]::FromHtml('#ededf0')
    $form.Font = New-Object Drawing.Font('Segoe UI', 10)
    $form.Padding = New-Object Windows.Forms.Padding(1)
    $form.Add_Paint({
        $_.Graphics.DrawRectangle([Drawing.Pens]::White, 0, 0, ($form.ClientSize.Width - 1), ($form.ClientSize.Height - 1))
    })
    $form.Add_Resize({ $form.Invalidate() })
    $form.KeyPreview = $true
    $form.Add_KeyDown({ if ($_.KeyCode -eq 'Escape') { $form.Close() } })
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false
    $form.TopMost = $true
    $form.Tag = 'later'
    $title = New-Object Windows.Forms.Label
    $title.Text = 'VODForge update needs attention'
    $title.SetBounds(22, 18, 530, 36)
    $title.Font = New-Object Drawing.Font('Segoe UI', 16, [Drawing.FontStyle]::Bold)
    $title.ForeColor = $form.ForeColor
    $title.Add_MouseDown({ if ($_.Button -eq 'Left') { $title.Tag = [Windows.Forms.Cursor]::Position } })
    $title.Add_MouseMove({
        if ($_.Button -eq 'Left' -and $title.Tag) {
            $point = [Windows.Forms.Cursor]::Position
            $form.Left += $point.X - $title.Tag.X
            $form.Top += $point.Y - $title.Tag.Y
            $title.Tag = $point
        }
    })
    $form.Controls.Add($title)
    $close = New-Object Windows.Forms.Button
    $close.Text = 'X'
    $close.SetBounds(562, 18, 36, 32)
    $close.Add_Click({ $form.Close() })
    $form.Controls.Add($close)
    $label = New-Object Windows.Forms.Label
    $label.SetBounds(22, 70, 576, 180)
    $label.Font = New-Object Drawing.Font('Segoe UI', 11)
    $label.Text = $messages[$Stage] + "`r`n`r`nRepair downloads the latest signed installer, backs up saved app data, and reinstalls in your current app folder. It does not uninstall VODForge or remove downloaded videos."
    $form.Controls.Add($label)
    $technical = New-Object Windows.Forms.TextBox
    $technical.SetBounds(22, 265, 576, 135)
    $technical.BackColor = [Drawing.ColorTranslator]::FromHtml('#111318')
    $technical.ForeColor = $form.ForeColor
    $technical.BorderStyle = 'None'
    $technical.Multiline = $true
    $technical.ReadOnly = $true
    $technical.ScrollBars = 'Vertical'
    $technical.Text = 'Stage: ' + $Stage + "`r`n" + $Detail + "`r`nApp folder: " + $Directory + "`r`nSaved-data backup: " + $Backup
    $technical.Visible = $false
    $form.Controls.Add($technical)
    $details = New-Object Windows.Forms.Button
    $details.Text = 'Technical details'
    $details.SetBounds(22, 265, 140, 32)
    $center = {
        $area = [Windows.Forms.Screen]::PrimaryScreen.WorkingArea
        if ($windowBounds -and $windowBounds.Count -eq 4) {
            $cx = [int]($windowBounds[0] + $windowBounds[2] / 2)
            $cy = [int]($windowBounds[1] + $windowBounds[3] / 2)
            $point = New-Object Drawing.Point($cx, $cy)
            $area = [Windows.Forms.Screen]::FromPoint($point).WorkingArea
        } else { $cx = $area.Left + $area.Width / 2; $cy = $area.Top + $area.Height / 2 }
        $left = [Math]::Max($area.Left, [Math]::Min($cx - $form.Width / 2, $area.Right - $form.Width))
        $top = [Math]::Max($area.Top, [Math]::Min($cy - $form.Height / 2, $area.Bottom - $form.Height))
        $form.Location = New-Object Drawing.Point([int]$left, [int]$top)
    }
    $details.Add_Click({
        $technical.Visible = !$technical.Visible
        if ($technical.Visible) { $form.ClientSize = New-Object Drawing.Size(620, 550); $details.Top = 410; $repair.Top = 495; $download.Top = 495; $later.Top = 495 }
        else { $form.ClientSize = New-Object Drawing.Size(620, 405); $details.Top = 265; $repair.Top = 350; $download.Top = 350; $later.Top = 350 }
        & $center
    })
    $form.Controls.Add($details)
    $repair = New-Object Windows.Forms.Button
    $repair.Text = 'Repair VODForge'
    $repair.SetBounds(448, 350, 150, 34)
    $repair.Enabled = $Stage -ne 'checking_data'
    $repair.Add_Click({ $form.Tag = 'repair'; $form.Close() })
    $form.Controls.Add($repair)
    $download = New-Object Windows.Forms.Button
    $download.Text = 'Open download page'
    $download.SetBounds(255, 350, 180, 34)
    $download.Add_Click({
        $label.Text = "On the release page, expand Assets and download VODForge-Windows-Setup. Close VODForge, open that downloaded file, keep the app folder below selected, and click Install. Do not uninstall first.`r`n`r`nApp folder: " + $Directory
        try { Start-Process 'https://github.com/SnowfallHD/vodforge/releases/latest' }
        catch { $label.Text += "`r`nOpen your browser and go to github.com/SnowfallHD/vodforge/releases/latest." }
    })
    $form.Controls.Add($download)
    $later = New-Object Windows.Forms.Button
    $later.Text = 'Later'
    $later.SetBounds(22, 350, 85, 34)
    $later.Add_Click({ $form.Close() })
    $form.Controls.Add($later)
    foreach ($button in @($repair, $download, $later, $details, $close)) {
        $button.FlatStyle = 'Flat'
        $button.FlatAppearance.BorderSize = 0
        $button.BackColor = [Drawing.ColorTranslator]::FromHtml('#191d24')
        $button.ForeColor = $form.ForeColor
        $button.Cursor = [Windows.Forms.Cursors]::Hand
    }
    $repair.BackColor = [Drawing.ColorTranslator]::FromHtml('#7170ff')
    $repair.ForeColor = [Drawing.Color]::White
    $form.AcceptButton = $repair
    $form.CancelButton = $later
    & $center
    [void]$form.ShowDialog()
    $choice = $form.Tag
    $form.Dispose()
    return $choice
}
"""
