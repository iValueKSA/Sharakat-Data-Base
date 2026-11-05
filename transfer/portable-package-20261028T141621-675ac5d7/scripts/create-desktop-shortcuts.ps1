$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$desktop = [Environment]::GetFolderPath('Desktop')
$shell = New-Object -ComObject WScript.Shell
foreach ($item in @(@('Start Investment Platform','Start Platform.bat'),@('Stop Investment Platform','Stop Platform.bat'),@('Restart Investment Platform','Restart Platform.bat'),@('Platform Status','Platform Status.bat'),@('Open Investment Platform','Open Platform.bat'))) {
    $shortcut = $shell.CreateShortcut((Join-Path $desktop ($item[0] + '.lnk')))
    $shortcut.TargetPath = Join-Path $project $item[1]
    $shortcut.WorkingDirectory = $project
    $shortcut.Description = $item[0]
    $shortcut.Save()
}
Write-Host 'Desktop shortcuts created.'
