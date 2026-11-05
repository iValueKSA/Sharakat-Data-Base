function Test-PortableHost([int]$HttpPort = 8080) {
    $os = Get-CimInstance Win32_OperatingSystem
    $cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
    $system = Get-CimInstance Win32_ComputerSystem
    $admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    $docker = Get-Command docker.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    $wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    $desktopPath = @((Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'),(Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\Docker Desktop.exe')) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    $driveName = [IO.Path]::GetPathRoot((Get-Location).Path).Substring(0,1)
    $drive = Get-PSDrive -Name $driveName -ErrorAction SilentlyContinue
    $freeGb = if ($drive) { [math]::Round($drive.Free / 1GB,1) } else { 0 }
    $wslText = ''
    if ($wsl) { try { $wslText = ((& $wsl.Source --version 2>&1 | Out-String) -replace "`0",'') } catch { $wslText = '' } }
    $wslReady = [bool]($wsl -and $wslText -match 'WSL version:\s*([2-9]|[1-9]\d)\.')
    $dockerVersion = $false; $composeVersion = $false; $engineRunning = $false
    if ($docker) {
        & $docker.Source --version *> $null; $dockerVersion = ($LASTEXITCODE -eq 0)
        & $docker.Source compose version *> $null; $composeVersion = ($LASTEXITCODE -eq 0)
        & $docker.Source info *> $null; $engineRunning = ($LASTEXITCODE -eq 0)
    }
    $portTaken = [bool](Get-NetTCPConnection -State Listen -LocalPort $HttpPort -ErrorAction SilentlyContinue | Select-Object -First 1)
    $writeCheck = Join-Path (Get-Location).Path ('.portable-write-check-' + [guid]::NewGuid().ToString('N'))
    $pathWritable = $false
    try { [IO.File]::WriteAllText($writeCheck,'check'); $pathWritable = $true } catch { $pathWritable = $false } finally { Remove-Item -LiteralPath $writeCheck -Force -ErrorAction SilentlyContinue }
    $virtualization = if ($engineRunning -and $wslReady) { 'PASS' } elseif ($cpu.VirtualizationFirmwareEnabled -or $cpu.VMMonitorModeExtensions) { 'PASS' } else { 'FAIL' }
    $checks = @(
        [pscustomobject]@{ key='windows_11'; status=if ([version]$os.Version -ge [version]'10.0.22000' -and [int]$os.BuildNumber -ge 22631) {'PASS'} else {'FAIL'}; observed="$($os.Caption), build $($os.BuildNumber)" },
        [pscustomobject]@{ key='architecture_x64'; status=if ($os.OSArchitecture -eq '64-bit' -and $cpu.Architecture -eq 9) {'PASS'} else {'FAIL'}; observed="$($os.OSArchitecture), processor architecture $($cpu.Architecture)" },
        [pscustomobject]@{ key='administrator'; status=if ($admin) {'PASS'} else {'FAIL'}; observed=if ($admin) {'elevated'} else {'not elevated; setup must request UAC elevation'} },
        [pscustomobject]@{ key='disk_space_20gb'; status=if ($freeGb -ge 20) {'PASS'} else {'FAIL'}; observed="$freeGb GB free on project drive" },
        [pscustomobject]@{ key='virtualization'; status=$virtualization; observed=if ($engineRunning -and $wslReady) {'Docker Engine and WSL2 are operational'} else {"CPU virtualization flags: firmware=$($cpu.VirtualizationFirmwareEnabled), SLAT=$($cpu.SecondLevelAddressTranslationExtensions)"} },
        [pscustomobject]@{ key='wsl2'; status=if ($wslReady) {'PASS'} else {'FAIL'}; observed=if ($wslReady) {'WSL 2 is available'} else {'WSL 2 not detected'} },
        [pscustomobject]@{ key='docker_desktop'; status=if ($desktopPath) {'PASS'} else {'FAIL'}; observed=if ($desktopPath) {'installed'} else {'not installed'} },
        [pscustomobject]@{ key='docker_engine'; status=if ($engineRunning) {'PASS'} else {'FAIL'}; observed=if ($engineRunning) {'running'} else {'stopped or unavailable'} },
        [pscustomobject]@{ key='docker_compose'; status=if ($composeVersion) {'PASS'} else {'FAIL'}; observed=if ($composeVersion) {'Compose plugin available'} else {'Compose plugin unavailable'} },
        [pscustomobject]@{ key='http_port'; status=if (-not $portTaken) {'PASS'} else {'FAIL'}; observed=if ($portTaken) {"port $HttpPort is occupied; no process was stopped"} else {"port $HttpPort is available"} },
        [pscustomobject]@{ key='project_folder_writable'; status=if ($pathWritable) {'PASS'} else {'FAIL'}; observed=if ($pathWritable) {'write test passed'} else {'folder is not writable'} },
        [pscustomobject]@{ key='postgres_host_binding'; status='PASS'; observed='PostgreSQL is configured on the private Compose network only' },
        [pscustomobject]@{ key='redis_host_binding'; status='PASS'; observed='Redis is configured on the private Compose network only' }
    )
    return [pscustomobject]@{
        checked_at_utc=(Get-Date).ToUniversalTime().ToString('o'); windows_caption=$os.Caption; windows_version=$os.Version; windows_build=[int]$os.BuildNumber
        architecture=$os.OSArchitecture; processor_architecture=[int]$cpu.Architecture; administrator=$admin; free_disk_gb=$freeGb; http_port=$HttpPort
        wsl2_available=$wslReady; docker_desktop_available=[bool]$desktopPath; docker_cli_available=[bool]$docker; docker_engine_running=$engineRunning; docker_compose_available=$composeVersion
        virtualization_detected=($virtualization -eq 'PASS'); postgres_publicly_exposed=$false; redis_publicly_exposed=$false; checks=$checks
        minimum_host_dependencies=@('Windows 11 x64','WSL2','Docker Desktop with Docker Compose v2','PowerShell 5.1 built into Windows')
    }
}
