param([switch]$ConfigureWsl)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$LogDirectory = Join-Path $ProjectRoot 'logs'
$LogPath = Join-Path $LogDirectory 'local-requirements-diagnostic.log'
$SetupDirectory = Join-Path $ProjectRoot '.local-setup'
$RebootMarker = Join-Path $SetupDirectory 'reboot-required'
New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
New-Item -ItemType Directory -Path $SetupDirectory -Force | Out-Null

function Write-SetupLog([string]$Message) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
    Write-Host $Message
    Add-Content -LiteralPath $LogPath -Value $line -Encoding UTF8
}

function Get-CommandPath([string]$Name) {
    $command = Get-Command $Name -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command) { return $command.Source }
    return 'NOT_FOUND'
}

function Get-DockerCliPath {
    $fromPath = Get-Command docker.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($fromPath) { return $fromPath.Source }
    $candidates = @(
        (Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin\docker.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe')
    )
    return ($candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1)
}

function Test-IsAdministrator {
    $principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Set-RebootRequiredMarker([string]$Reason) {
    $lastBoot = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime().ToString('o')
    Set-Content -LiteralPath $RebootMarker -Value @("BootTimeUtc=$lastBoot", "Reason=$Reason") -Encoding UTF8
}

function Write-Diagnostic {
    $os = Get-CimInstance Win32_OperatingSystem
    $system = Get-CimInstance Win32_ComputerSystem
    $product = Get-CimInstance Win32_ComputerSystemProduct
    $processors = @(Get-CimInstance Win32_Processor)
    $cpu = $processors | Select-Object -First 1
    $deviceGuard = Get-CimInstance -Namespace 'root\Microsoft\Windows\DeviceGuard' -ClassName Win32_DeviceGuard -ErrorAction SilentlyContinue
    $desktopCandidates = @(
        (Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\Docker Desktop.exe')
    )
    $desktopPath = $desktopCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    $dockerPath = Get-DockerCliPath
    if (-not $dockerPath) { $dockerPath = 'NOT_FOUND' }
    $wslPath = Get-CommandPath 'wsl.exe'
    $wingetPath = Get-CommandPath 'winget.exe'
    $wslVersionText = 'NOT_CHECKED'
    $wslStatusText = 'NOT_CHECKED'
    if ($wslPath -ne 'NOT_FOUND') {
        try { $wslVersionText = ((& $wslPath --version 2>&1 | Out-String) -replace "`0",'').Trim() }
        catch { $wslVersionText = ([string]$_.Exception.Message -replace "`0",'').Trim() }
        try { $wslStatusText = ((& $wslPath --status 2>&1 | Out-String) -replace "`0",'').Trim() }
        catch { $wslStatusText = ([string]$_.Exception.Message -replace "`0",'').Trim() }
    }
    $dockerEngine = 'NOT_INSTALLED'
    if ($dockerPath -ne 'NOT_FOUND') {
        try {
            & $dockerPath info *> $null
            if ($LASTEXITCODE -eq 0) { $dockerEngine = 'RUNNING' } else { $dockerEngine = 'STOPPED' }
        } catch { $dockerEngine = 'STOPPED' }
    }
    $hyperVFeatures = 'UNKNOWN_REQUIRES_ELEVATION'
    if (Test-IsAdministrator) {
        try {
            $featureNames = @('Microsoft-Hyper-V-All','VirtualMachinePlatform','Microsoft-Windows-Subsystem-Linux')
            $states = foreach ($featureName in $featureNames) {
                $feature = Get-WindowsOptionalFeature -Online -FeatureName $featureName -ErrorAction Stop
                "$featureName=$($feature.State)"
            }
            $hyperVFeatures = $states -join '; '
        } catch { $hyperVFeatures = "QUERY_FAILED: $($_.Exception.Message)" }
    }
    $wingetPackage = 'NOT_CHECKED'
    if ($wingetPath -ne 'NOT_FOUND') {
        try {
            $searchText = ((& $wingetPath search --id Docker.DockerDesktop --exact --source winget --accept-source-agreements 2>&1 | Out-String) -replace "`0",'')
            if ($LASTEXITCODE -eq 0 -and $searchText -match 'Docker\.DockerDesktop') { $wingetPackage = 'VERIFIED_IN_WINGET_SOURCE' }
            else { $wingetPackage = 'NOT_VERIFIED' }
        } catch { $wingetPackage = 'NOT_VERIFIED' }
    }
    $fields = [ordered]@{
        WindowsCaption = $os.Caption
        WindowsVersion = $os.Version
        WindowsBuild = $os.BuildNumber
        WindowsEditionSKU = $os.OperatingSystemSKU
        Architecture = $os.OSArchitecture
        Manufacturer = $system.Manufacturer
        Model = $system.Model
        ProductName = $product.Name
        CpuName = $cpu.Name
        CpuArchitectureBits = $cpu.AddressWidth
        CpuVirtualizationFirmwareEnabled = $cpu.VirtualizationFirmwareEnabled
        CpuVMMonitorModeExtensions = $cpu.VMMonitorModeExtensions
        CpuSLAT = $cpu.SecondLevelAddressTranslationExtensions
        HypervisorPresent = $system.HypervisorPresent
        VBSStatus = if ($deviceGuard) { $deviceGuard.VirtualizationBasedSecurityStatus } else { 'UNKNOWN' }
        VBSRunningServices = if ($deviceGuard) { ($deviceGuard.SecurityServicesRunning -join ',') } else { 'UNKNOWN' }
        TotalMemoryGB = [math]::Round($system.TotalPhysicalMemory / 1GB, 1)
        IsAdministrator = (Test-IsAdministrator)
        DockerDesktop = if ($desktopPath) { $desktopPath } else { 'NOT_INSTALLED' }
        DockerCLI = $dockerPath
        DockerEngine = $dockerEngine
        WinGet = $wingetPath
        WinGetDockerPackage = $wingetPackage
        WSL = $wslPath
        WSLVersionOutput = ($wslVersionText -replace '[\r\n]+',' | ')
        WSLStatusOutput = ($wslStatusText -replace '[\r\n]+',' | ')
        HyperVAndWSLFeatureStates = $hyperVFeatures
        DockerVMM = 'NOT_SELECTED: Docker documents Docker VMM as Beta; WSL2 is the default mature backend selected for this Linux-container stack. Hyper-V remains a supported all-users alternative.'
    }
    foreach ($key in $fields.Keys) {
        $safeValue = [string]$fields[$key]
        Write-SetupLog "$key=$safeValue"
    }
    return $fields
}

function Invoke-ElevatedWslSetup {
    if (-not (Test-IsAdministrator)) {
        Write-SetupLog 'CONFIGURED: requesting standard Windows UAC elevation to enable WSL2 components.'
        $powershell = (Get-Command powershell.exe).Source
        $argumentList = @('-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-File',('"' + $PSCommandPath + '"'),'-ConfigureWsl')
        try {
            $process = Start-Process -FilePath $powershell -ArgumentList $argumentList -Verb RunAs -PassThru -Wait
        } catch {
            throw 'DOCKER_INSTALLATION_USER_ACTION_REQUIRED: approve the normal Windows UAC prompt to enable WSL2, then run Install Platform Requirements again.'
        }
        if ($process.ExitCode -ne 0) { throw "The elevated WSL setup failed with exit code $($process.ExitCode). Review the diagnostic log." }
        return
    }
    Write-SetupLog 'Configuring WSL2 using the built-in Microsoft installer (no Linux distribution requested).'
    $wsl = Get-CommandPath 'wsl.exe'
    $output = & $wsl --install --no-distribution 2>&1
    $exitCode = $LASTEXITCODE
    foreach ($line in $output) { Write-SetupLog "WSL: $line" }
    if ($exitCode -ne 0 -and $exitCode -ne 3010) { throw "WSL2 setup failed with exit code $exitCode. Check virtualization and review the diagnostic log." }
    Set-RebootRequiredMarker 'WSL2 features or kernel setup was requested.'
    Write-SetupLog 'REBOOT_REQUIRED: Windows must restart to finish WSL2 prerequisite setup.'
    Write-Host ''
    Write-Host 'A Windows restart is required to finish the platform setup.' -ForegroundColor Yellow
    Write-Host 'Please restart your computer.'
    Write-Host 'After Windows starts, double-click: Install Platform Requirements'
}

function Test-WslReady([System.Collections.IDictionary]$Diagnostics) {
    if ($Diagnostics.WSL -eq 'NOT_FOUND') { return $false }
    $text = [string]$Diagnostics.WSLVersionOutput
    if ($text -match 'not installed|not recognized|install by running') { return $false }
    if ($text -match 'WSL version:\s*(\d+)\.(\d+)\.(\d+)') {
        $version = [version]::new([int]$Matches[1],[int]$Matches[2],[int]$Matches[3])
        return ($version -ge [version]'2.1.5')
    }
    return $false
}

function Test-WindowsSupported([System.Collections.IDictionary]$Diagnostics) {
    $isWindows11 = [version]$Diagnostics.WindowsVersion -ge [version]'10.0.22000'
    $supportedEdition = $Diagnostics.WindowsCaption -match 'Pro|Enterprise|Education'
    $supportedArchitecture = $Diagnostics.Architecture -match '64-bit|ARM64'
    $build = [int]$Diagnostics.WindowsBuild
    if (-not $isWindows11 -or -not $supportedEdition -or -not $supportedArchitecture -or $build -lt 22631) {
        throw "Unsupported Windows environment. Docker Desktop currently requires supported, serviced Windows 11 Pro/Enterprise/Education x64 or a supported Windows 10 release. Detected: $($Diagnostics.WindowsCaption), build $build, $($Diagnostics.Architecture). Update to a supported Windows version; no unsupported workaround was attempted."
    }
}

try {
    Write-SetupLog '=== Local platform requirements diagnostic and installer ==='
    $diagnostics = Write-Diagnostic
    if (Test-Path -LiteralPath $RebootMarker) {
        $marker = Get-Content -LiteralPath $RebootMarker
        $recordedBoot = (($marker | Where-Object { $_ -like 'BootTimeUtc=*' } | Select-Object -First 1) -replace '^BootTimeUtc=','')
        $currentBoot = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime().ToString('o')
        if ($recordedBoot -and $recordedBoot -eq $currentBoot) {
            Write-Host ''
            Write-Host 'A Windows restart is required to finish the platform setup.' -ForegroundColor Yellow
            Write-Host 'Please restart your computer.'
            Write-Host 'After Windows starts, double-click: Install Platform Requirements'
            exit 0
        }
        Remove-Item -LiteralPath $RebootMarker -Force
        Write-SetupLog 'CONFIGURED: Windows restarted since the prerequisite change; resuming setup.'
    }
    Test-WindowsSupported -Diagnostics $diagnostics

    if ($diagnostics.TotalMemoryGB -lt 8) { throw "Docker Desktop requires at least 8 GB RAM; this computer reports $($diagnostics.TotalMemoryGB) GB." }
    if (-not (Test-WslReady -Diagnostics $diagnostics)) {
        if ($PSBoundParameters.ContainsKey('ConfigureWsl')) {
            Write-SetupLog 'Enabling the Microsoft WSL and Virtual Machine Platform features. No Linux distribution will be installed.'
            $wsl = Get-CommandPath 'wsl.exe'
            $wslOutput = & $wsl --install --no-distribution 2>&1
            $wslExitCode = $LASTEXITCODE
            foreach ($line in $wslOutput) { Write-SetupLog ("WSL: " + ([string]$line -replace "`0",'')) }
            if ($wslExitCode -ne 0 -and $wslExitCode -ne 3010) {
                throw "Microsoft WSL2 feature setup failed with exit code $wslExitCode. Review Windows virtualization/firmware settings and the diagnostic log."
            }
            Set-RebootRequiredMarker 'WSL2 features or kernel setup was requested.'
            Write-SetupLog 'REBOOT_REQUIRED: Windows must restart to finish WSL2 prerequisite setup.'
            Write-Host ''
            Write-Host 'A Windows restart is required to finish the platform setup.' -ForegroundColor Yellow
            Write-Host 'Please restart your computer.'
            Write-Host 'After Windows starts, double-click: Install Platform Requirements'
            exit 0
        }
        Invoke-ElevatedWslSetup
        exit 0
    }
    if ($diagnostics.WSLStatusOutput -match 'WSL2 is unable to start since virtualization is not enabled|virtualization is not enabled on this machine') {
        throw 'DOCKER_INSTALLATION_USER_ACTION_REQUIRED: after the required Windows restart, WSL still reports that hardware virtualization is unavailable. Windows edition: Windows 11 Pro. Virtualization state: WSL2 cannot start and the processor extension flags are not exposed as enabled. Recommended backend: WSL2. Exact action: enable Intel Virtualization Technology (VT-x) in the Lenovo BIOS/UEFI setup, save changes, restart Windows, then double-click Install Platform Requirements again. No unsupported workaround was attempted.'
    }
    if ($diagnostics.WinGet -eq 'NOT_FOUND' -or $diagnostics.WinGetDockerPackage -ne 'VERIFIED_IN_WINGET_SOURCE') {
        throw 'DOCKER_INSTALLATION_USER_ACTION_REQUIRED: WinGet did not verify the exact official Docker Desktop package. Install Docker Desktop only from Docker official distribution, then rerun this installer.'
    }

    if ($diagnostics.DockerDesktop -eq 'NOT_INSTALLED') {
        Write-SetupLog 'Installing verified Docker Desktop package through WinGet.'
        $winget = $diagnostics.WinGet
        & $winget install --id Docker.DockerDesktop --exact --source winget --accept-package-agreements --accept-source-agreements --silent --disable-interactivity 2>&1 | ForEach-Object { Write-SetupLog "WinGet: $_" }
        if ($LASTEXITCODE -ne 0) {
            if ($LASTEXITCODE -eq -1978335189 -or $LASTEXITCODE -eq 3010) {
                Set-RebootRequiredMarker 'Docker Desktop installer requested a Windows restart.'
                Write-SetupLog 'REBOOT_REQUIRED: Docker Desktop installation requested a restart.'
                Write-Host 'A Windows restart is required. Restart, then double-click Install Platform Requirements.' -ForegroundColor Yellow
                exit 0
            }
            throw "Docker Desktop installation failed with exit code $LASTEXITCODE. Review the diagnostic log."
        }
        Write-SetupLog 'INSTALLED: Docker Desktop.'
    } else { Write-SetupLog 'ALREADY_INSTALLED: Docker Desktop.' }

    $desktop = @(
        (Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\Docker Desktop.exe')
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    $docker = Get-DockerCliPath
    if (-not $desktop -or -not $docker) { throw 'Docker Desktop installed, but its application or CLI is not available yet. Restart Windows if requested, then rerun this installer.' }
    Write-SetupLog 'Starting Docker Desktop...'
    if (-not (Get-Process -Name 'Docker Desktop' -ErrorAction SilentlyContinue)) { Start-Process -FilePath $desktop | Out-Null }
    Write-SetupLog 'Waiting for Docker Engine...'
    $engineReady = $false
    for ($i = 0; $i -lt 180; $i++) {
        try {
            & $docker info *> $null
            if ($LASTEXITCODE -eq 0) { $engineReady = $true; break }
        } catch { }
        if (($i % 10) -eq 0) { Write-Host 'Waiting for Docker Engine...' }
        Start-Sleep -Seconds 5
    }
    if (-not $engineReady) { throw 'Docker Engine did not become ready within 15 minutes. Finish Docker Desktop first-run setup/terms if shown, then rerun this installer.' }
    Write-SetupLog 'ALREADY_INSTALLED: Docker Engine is running.'
    & $docker compose version
    if ($LASTEXITCODE -ne 0) { throw 'Docker Compose v2 is unavailable. Update or repair Docker Desktop.' }
    Write-SetupLog 'ALREADY_INSTALLED: Docker Compose v2.'

    Set-Location -LiteralPath $ProjectRoot
    $startBat = Join-Path $ProjectRoot 'Start Platform.bat'
    if (-not (Test-Path -LiteralPath $startBat)) { throw 'Start Platform.bat is missing from the project root.' }
    Write-SetupLog 'Starting the local platform to complete first-run setup.'
    $commandProcessor = Join-Path $env:WINDIR 'System32\cmd.exe'
    $startCommand = '"' + $startBat + '"'
    & $commandProcessor /d /c $startCommand
    $startExitCode = $LASTEXITCODE
    if ($startExitCode -ne 0) { throw "Start Platform returned exit code $startExitCode. See logs\startup.log; the existing SQLite database and backup were left intact." }
    Remove-Item -LiteralPath $RebootMarker -Force -ErrorAction SilentlyContinue
    Write-SetupLog 'PASS: Docker Desktop and the local platform startup completed.'
    Write-Host 'Setup complete. The platform should be open in your browser at http://localhost:8080' -ForegroundColor Green
} catch {
    Write-SetupLog "FAILED_OR_USER_ACTION_REQUIRED: $($_.Exception.Message)"
    Write-Host "`n$($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Diagnostic log: $LogPath"
    exit 1
}
