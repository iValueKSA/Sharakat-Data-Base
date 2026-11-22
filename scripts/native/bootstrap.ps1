<#
  Windows bootstrap for the native (Docker-free) runtime.
  Ensures Python 3.12 and a private virtual environment, then runs
  `python -m sharakat_runtime <args>` from the project root.
  No administrator rights are needed: Python is installed per user.
#>
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$RuntimeArgs)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$HomeDir = if ($env:SHARAKAT_HOME) { $env:SHARAKAT_HOME } else { Join-Path $env:LOCALAPPDATA 'Sharakat' }
$VenvDir = Join-Path $HomeDir 'venv'
$VenvPython = Join-Path $VenvDir 'Scripts\python.exe'
$LogDir = Join-Path $HomeDir 'logs'
New-Item -ItemType Directory -Force -Path $HomeDir, $LogDir | Out-Null

# python.org stopped shipping Windows installers after 3.12.10 (later 3.12.x are source-only security releases).
$PythonVersion = '3.12.10'
$Installers = @{
  'AMD64' = @{ Url = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-amd64.exe"; Sha256 = '67b5635e80ea51072b87941312d00ec8927c4db9ba18938f7ad2d27b328b95fb' }
  'ARM64' = @{ Url = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-arm64.exe"; Sha256 = '377ac8fd478987940088e879441e702a71b53164d2a1e6f1d51ff77a7e470258' }
}

function Test-Python([string]$Exe, [string[]]$Prefix = @()) {
  $previous = $ErrorActionPreference
  try {
    $ErrorActionPreference = 'Continue'   # a missing version must not abort the search
    # No double quotes inside the -c code: Windows PowerShell 5.1 strips them
    # from native-command arguments, which turned this check into a SyntaxError.
    $out = & $Exe @Prefix -c 'import sys; print(sys.version_info[0], sys.version_info[1], sep=chr(46))' 2>$null
    if ($LASTEXITCODE -eq 0 -and "$out".Trim() -match '^3\.(\d+)$' -and [int]$Matches[1] -ge 12) { return $true }
  } catch { } finally { $ErrorActionPreference = $previous }
  return $false
}

function Find-Python {
  $py = Get-Command py.exe -ErrorAction SilentlyContinue
  if ($py) {
    foreach ($v in '-3.12', '-3.13') { if (Test-Python $py.Source @($v)) { return @($py.Source, $v) } }
  }
  $candidates = @(
    (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'),
    (Join-Path $env:ProgramFiles 'Python312\python.exe')
  )
  foreach ($c in $candidates) { if ((Test-Path $c) -and (Test-Python $c)) { return @($c) } }
  return $null
}

function Install-Python {
  Write-Host 'Python 3.12 was not found. Installing it for this Windows user...'
  $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
  if ($winget) {
    & $winget.Source install --exact --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements | Out-Host
    if (Find-Python) { return }
  }
  $arch = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'ARM64' } else { 'AMD64' }
  $pin = $Installers[$arch]
  $installer = Join-Path $HomeDir "downloads\python-$PythonVersion-$arch.exe"
  New-Item -ItemType Directory -Force -Path (Split-Path $installer) | Out-Null
  Write-Host "Downloading $($pin.Url)"
  Invoke-WebRequest -Uri $pin.Url -OutFile $installer -UseBasicParsing
  $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $installer).Hash.ToLowerInvariant()
  if ($hash -ne $pin.Sha256) { Remove-Item -LiteralPath $installer -Force; throw "Python installer checksum mismatch ($hash)." }
  $p = Start-Process -FilePath $installer -ArgumentList '/quiet', 'InstallAllUsers=0', 'PrependPath=0', 'Include_test=0', 'Include_launcher=1', 'InstallLauncherAllUsers=0' -Wait -PassThru
  if ($p.ExitCode -ne 0) { throw "Python installer failed with exit code $($p.ExitCode)." }
}

$python = Find-Python
if (-not $python) { Install-Python; $python = Find-Python }
if (-not $python) { throw 'Python 3.12 could not be installed. Install it from python.org and run this again.' }

# Private virtual environment, rebuilt when requirements.txt changes.
$requirements = Join-Path $ProjectRoot 'requirements.txt'
$reqHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $requirements).Hash
$stamp = Join-Path $VenvDir '.requirements.sha256'
if (-not (Test-Path $VenvPython)) {
  Write-Host 'Creating the private Python environment...'
  $exe = $python[0]; $prefix = @($python | Select-Object -Skip 1)
  & $exe @prefix -m venv $VenvDir
  if ($LASTEXITCODE -ne 0) { throw 'Creating the virtual environment failed.' }
}
if (-not (Test-Path $stamp) -or (Get-Content -LiteralPath $stamp -Raw).Trim() -ne $reqHash) {
  Write-Host 'Installing Python packages (first run only, a few minutes)...'
  $pipLog = Join-Path $LogDir 'pip.log'
  # Windows PowerShell 5.1 turns redirected native stderr (pip warnings) into
  # terminating errors under 'Stop'; let cmd.exe do the redirection instead.
  cmd.exe /d /c "`"$VenvPython`" -m pip install --disable-pip-version-check --upgrade pip >> `"$pipLog`" 2>&1"
  cmd.exe /d /c "`"$VenvPython`" -m pip install --disable-pip-version-check -r `"$requirements`" >> `"$pipLog`" 2>&1"
  if ($LASTEXITCODE -ne 0) { throw "Installing Python packages failed. See $pipLog" }
  Set-Content -LiteralPath $stamp -Value $reqHash -Encoding ascii
}

Set-Location -LiteralPath $ProjectRoot
& $VenvPython -m sharakat_runtime @RuntimeArgs
exit $LASTEXITCODE
