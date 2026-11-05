param(
    [switch]$CheckOnly,
    [switch]$TestMode,
    [Security.SecureString]$TransferPassphraseSecureString
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = Split-Path -Parent $PSCommandPath
Set-Location -LiteralPath $root
$logDir = Join-Path $root 'logs'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$logPath = Join-Path $logDir ('setup-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')
. (Join-Path $root 'scripts\portable-crypto.ps1')
. (Join-Path $root 'scripts\portable-host-check.ps1')

function Write-SetupLog([string]$Message) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
    Write-Host $Message
    Add-Content -LiteralPath $logPath -Value $line -Encoding UTF8
}

function Find-DockerCli {
    $command = Get-Command docker.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command) { return $command.Source }
    $candidates = @((Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin\docker.exe'),(Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'))
    return ($candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1)
}

function Get-ComposePrefix([string]$ProjectName) {
    return @('compose','--env-file','.env.local','-f','docker-compose.yml','-f','docker-compose.portable.yml','-p',$ProjectName)
}

function Invoke-PortableCompose([string]$ProjectName,[string[]]$Arguments,[switch]$AllowFailure) {
    $dockerArgs = (Get-ComposePrefix $ProjectName) + $Arguments
    $previousErrorAction = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = & $script:DockerPath @dockerArgs 2>&1
        $script:LastComposeExit = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previousErrorAction }
    if ($output -and $script:SetupLogEnabled) { $output | Out-File -LiteralPath $logPath -Append -Encoding UTF8 }
    if ($script:LastComposeExit -ne 0 -and -not $AllowFailure) { throw "A platform preparation step failed (exit $script:LastComposeExit). See the setup log for details." }
    return ($output -join [Environment]::NewLine)
}

function Write-PrivateFile([string]$Path,[string]$Content) {
    [IO.File]::WriteAllText($Path,$Content,[Text.UTF8Encoding]::new($false))
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    & icacls.exe $Path '/inheritance:r' '/grant:r' ("${identity}:(F)") *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Could not restrict access to the destination environment file.' }
}

function Save-Progress([string]$Phase,[string]$ProjectName) {
    $record = [ordered]@{ schema_version=1; phase=$Phase; compose_project_name=$ProjectName; updated_at_utc=(Get-Date).ToUniversalTime().ToString('o'); test_mode=[bool]$TestMode }
    [IO.File]::WriteAllText($script:ProgressPath,($record | ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
}

function Set-InstallationState([string]$Phase,[string]$ProjectName,[int]$Port,[string]$Subnet) {
    $record = [ordered]@{ schema_version=1; mode='portable'; status=$Phase; composeProjectName=$ProjectName; hostPort=$Port; baseUrl="http://localhost:$Port"; composeSubnet=$Subnet; created_at_utc=(Get-Date).ToUniversalTime().ToString('o'); sourceSyncStarted=$false }
    [IO.File]::WriteAllText($script:InstallStatePath,($record | ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
}

function Read-Json([string]$Path) { return (Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json) }

function Get-PortableSnapshot([string]$ProjectName) {
    $raw = Invoke-PortableCompose -ProjectName $ProjectName -Arguments @('run','--rm','--no-deps','-T','migrate','python','scripts/portable_transfer_snapshot.py')
    $jsonLine = @($raw -split "`r?`n" | Where-Object { $_.Trim().StartsWith('{') } | Select-Object -Last 1)
    if (-not $jsonLine) { throw 'The database reconciliation snapshot was not returned.' }
    return ($jsonLine[0] | ConvertFrom-Json)
}

function Test-ManifestSnapshot($Actual,$Expected) {
    $ignore = @('user_sessions')
    foreach ($property in $Expected.PSObject.Properties) {
        if ($ignore -contains $property.Name) { continue }
        $actualValue = $Actual.($property.Name) | ConvertTo-Json -Depth 8 -Compress
        $expectedValue = $Expected.($property.Name) | ConvertTo-Json -Depth 8 -Compress
        if ($actualValue -cne $expectedValue) { return $false }
    }
    return $true
}

function Test-TransferChecksums([string]$PackageRoot,$Manifest) {
    $checksumsPath = Join-Path $PackageRoot 'checksums.sha256'
    if (-not (Test-Path -LiteralPath $checksumsPath)) { throw 'The package checksum list is missing.' }
    $rootPrefix = [IO.Path]::GetFullPath($PackageRoot).TrimEnd('\') + '\'
    $checked = 0
    foreach ($line in (Get-Content -LiteralPath $checksumsPath)) {
        if (-not $line.Trim()) { continue }
        if ($line -notmatch '^([0-9a-f]{64})\s{2}(.+)$') { throw 'The checksum list contains an invalid record.' }
        $relative = $Matches[2].Replace('/','\')
        if ([IO.Path]::IsPathRooted($relative) -or $relative -match '(^|\\)\.\.(\\|$)') { throw 'The checksum list contains an unsafe path.' }
        $file = [IO.Path]::GetFullPath((Join-Path $PackageRoot $relative))
        if (-not $file.StartsWith($rootPrefix,[StringComparison]::OrdinalIgnoreCase)) { throw 'A checksum path resolves outside the transfer package.' }
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "A packaged artifact is missing: $relative" }
        if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -cne $Matches[1]) { throw "A packaged artifact checksum does not match: $relative" }
        $checked++
    }
    $manifestBackup = Join-Path $PackageRoot ([string]$Manifest.database_backup.path).Replace('/','\')
    if ((Get-FileHash -LiteralPath $manifestBackup -Algorithm SHA256).Hash.ToLowerInvariant() -cne [string]$Manifest.database_backup.sha256) { throw 'The logical database backup hash does not match the signed transfer manifest record.' }
    if ($checked -lt 20) { throw 'The package contains too few checksummed artifacts to be a complete platform transfer.' }
    return $checked
}

function Select-FreeNetwork([string]$ProjectName) {
    $ids = @(& $script:DockerPath 'network' 'ls' '-q' 2>$null | Where-Object { $_.Trim() })
    $used = @()
    if ($ids.Count) {
        $raw = & $script:DockerPath 'network' 'inspect' @ids '--format' '{{range .IPAM.Config}}{{println .Subnet}}{{end}}' 2>$null
        $used = @($raw | Where-Object { $_ -match '^172\.31\.\d+\.0/24$' })
    }
    $start = ([Convert]::ToInt32(([guid]::NewGuid().ToString('N').Substring(0,2)),16) % 12) + 241
    for ($offset=0; $offset -lt 14; $offset++) {
        $octet = 241 + (($start - 241 + $offset) % 14)
        $subnet = "172.31.$octet.0/24"
        if ($used -notcontains $subnet) { return [pscustomobject]@{ subnet=$subnet; frontendIp="172.31.$octet.10" } }
    }
    throw 'No unused private /24 subnet was found in the project network range.'
}

function Write-PortableEnvironment([string]$SessionSecret,[string]$ProjectName,[int]$Port,[string]$Subnet,[string]$FrontendIp) {
    $dbPassword = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
    $redisPassword = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
    $bootstrapFallback = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
    $cors = "http://localhost:$Port,http://127.0.0.1:$Port"
    $lines = @(
        'ENVIRONMENT=local_user','POSTGRES_DB=sharakat_local','POSTGRES_USER=sharakat_local',
        "POSTGRES_PASSWORD=$dbPassword","DATABASE_URL=postgresql+psycopg://sharakat_local:$dbPassword@db:5432/sharakat_local",
        "REDIS_PASSWORD=$redisPassword","REDIS_URL=redis://:$redisPassword@redis:6379/0","SECRET_KEY=$SessionSecret",
        "PUBLIC_BASE_URL=http://localhost:$Port","CORS_ORIGINS=$cors","FORWARDED_ALLOW_IPS=$FrontendIp",
        "COMPOSE_NETWORK_SUBNET=$Subnet","FRONTEND_CONTAINER_IP=$FrontendIp","FRONTEND_HOST_PORT=$Port",
        "BOOTSTRAP_ADMIN_EMAIL=admin@local","BOOTSTRAP_ADMIN_PASSWORD=$bootstrapFallback",
        'STAGING_DATABASE_NAME=sharakat_local','BACKUP_DIR=/backups','LOCAL_SQLITE_PATH=/source-data/al-ahsa-live.db',
        'LOCAL_EXPECTED_DATABASE=sharakat_local','LOCAL_SETUP_MARKER=local_setup_state',
        "PORTABLE_TRANSFER_TEST_MODE=$(if ($TestMode) {'1'} else {'0'})"
    )
    Write-PrivateFile -Path $script:EnvPath -Content (($lines -join "`r`n") + "`r`n")
}

function Get-DatabaseSchemaPresent([string]$ProjectName) {
    $raw = Invoke-PortableCompose -ProjectName $ProjectName -Arguments @('exec','-T','db','sh','-lc','psql -At -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT to_regclass(''public.opportunities'') IS NOT NULL"')
    return ($raw.Trim() -eq 't')
}

function Wait-DatabaseRedis([string]$ProjectName) {
    for ($attempt=0; $attempt -lt 60; $attempt++) {
        $ps = Invoke-PortableCompose -ProjectName $ProjectName -Arguments @('ps','--all','--format','json') -AllowFailure
        $services = @()
        foreach ($line in ($ps -split "`r?`n" | Where-Object { $_.Trim() })) { try { $services += ($line | ConvertFrom-Json) } catch { } }
        $db = $services | Where-Object { $_.Service -eq 'db' } | Select-Object -First 1
        $redis = $services | Where-Object { $_.Service -eq 'redis' } | Select-Object -First 1
        if ($db -and $redis -and $db.State -match 'running|up' -and $redis.State -match 'running|up' -and $db.Health -eq 'healthy' -and $redis.Health -eq 'healthy') { return }
        Start-Sleep -Seconds 3
    }
    throw 'PostgreSQL and Redis did not become healthy. The packaged backup was not restored.'
}

function Start-DockerRequirements([int]$Port) {
    $hostCheck = Test-PortableHost -HttpPort $Port
    $script:HostCheck = $hostCheck
    $hostPath = Join-Path $root 'docs\validation\deployment\portable-transfer\host-requirements.json'
    New-Item -ItemType Directory -Path (Split-Path -Parent $hostPath) -Force | Out-Null
    [IO.File]::WriteAllText($hostPath,($hostCheck | ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
    $osSupported = [version]$hostCheck.windows_version -ge [version]'10.0.22000' -and $hostCheck.windows_build -ge 22631 -and $hostCheck.architecture -eq '64-bit'
    if (-not $osSupported) { throw "Unsupported target system: $($hostCheck.windows_caption), build $($hostCheck.windows_build), $($hostCheck.architecture)." }
    if ($hostCheck.free_disk_gb -lt 20) { throw "At least 20 GB of free disk space is required; $($hostCheck.free_disk_gb) GB is available." }
    $writableCheck = $hostCheck.checks | Where-Object { $_.key -eq 'project_folder_writable' }
    if ($writableCheck.status -ne 'PASS') { throw 'The project folder is not writable.' }
    $adminCheck = $hostCheck.checks | Where-Object { $_.key -eq 'administrator' }
    if ($adminCheck.status -ne 'PASS' -and -not $TestMode -and -not $CheckOnly) { throw 'Administrator rights are required. Re-run Setup Platform.bat and approve the Windows UAC prompt.' }
    if (-not $hostCheck.wsl2_available) {
        if ($TestMode -or $CheckOnly) { throw 'WSL2 is not available on this machine.' }
        Write-SetupLog '[2/8] Installing WSL2 with the Microsoft Windows installer.'
        $wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
        if (-not $wsl) { throw 'Windows WSL is unavailable. Run Windows Update or use the official Microsoft WSL installation guidance.' }
        & $wsl.Source --install --no-distribution *> $null
        $exit = $LASTEXITCODE
        if ($exit -ne 0 -and $exit -ne 3010) { throw 'Windows could not install WSL2. Check virtualization in UEFI, then retry.' }
        Save-Progress -Phase 'REBOOT_REQUIRED_WSL' -ProjectName ''
        Write-Host 'يجب إعادة تشغيل الجهاز ثم تشغيل Setup Platform.bat مرة أخرى' -ForegroundColor Yellow
        return $false
    }
    $script:DockerPath = Find-DockerCli
    $desktop = @((Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'),(Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\Docker Desktop.exe')) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $desktop) {
        if ($TestMode -or $CheckOnly) { throw 'Docker Desktop is not installed.' }
        $winget = Get-Command winget.exe -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $winget) { throw 'Docker Desktop is not installed and WinGet is unavailable. Install Docker Desktop from the official Docker distribution, then run Setup Platform.bat again.' }
        Write-SetupLog '[3/8] Checking the official Docker Desktop WinGet package.'
        $wingetSearch = (& $winget.Source search --id Docker.DockerDesktop --exact --source winget --accept-source-agreements 2>&1 | Out-String)
        if ($LASTEXITCODE -ne 0 -or $wingetSearch -notmatch 'Docker\.DockerDesktop') { throw 'WinGet could not verify Docker.DockerDesktop from its official source. No installer was downloaded.' }
        Write-SetupLog 'Installing Docker Desktop from the verified WinGet package.'
        & $winget.Source install --id Docker.DockerDesktop --exact --source winget --accept-package-agreements --accept-source-agreements --silent --disable-interactivity *> $null
        if ($LASTEXITCODE -eq 3010) {
            Save-Progress -Phase 'REBOOT_REQUIRED_DOCKER' -ProjectName ''
            Write-Host 'يجب إعادة تشغيل الجهاز ثم تشغيل Setup Platform.bat مرة أخرى' -ForegroundColor Yellow
            return $false
        }
        if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop installation failed. Review Windows notifications and the setup log, then retry.' }
        $desktop = @((Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'),(Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\Docker Desktop.exe')) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    }
    $script:DockerPath = Find-DockerCli
    if (-not $desktop -or -not $script:DockerPath) { throw 'Docker Desktop or its command line is not available. Repair Docker Desktop and retry.' }
    if (-not $hostCheck.docker_engine_running) {
        Write-SetupLog 'Starting Docker Desktop and waiting for Docker Engine.'
        if (-not (Get-Process -Name 'Docker Desktop' -ErrorAction SilentlyContinue)) { Start-Process -FilePath $desktop | Out-Null }
        $engine = $false
        for ($i=0; $i -lt 180; $i++) { & $script:DockerPath info *> $null; if ($LASTEXITCODE -eq 0) { $engine=$true; break }; Start-Sleep -Seconds 5 }
        if (-not $engine) { throw 'Docker Engine is not ready. Complete Docker Desktop first-run setup, restart if requested, then retry.' }
    }
    & $script:DockerPath compose version *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Docker Compose v2 is unavailable. Update Docker Desktop and retry.' }
    return $true
}

try {
    $script:SetupLogEnabled = $true
    $script:InstallStatePath = Join-Path $root '.installation-state.json'
    $script:ProgressPath = Join-Path $root 'transfer\.portable-setup-state.json'
    $script:EnvPath = Join-Path $root '.env.local'
    $port = if ($TestMode) { 18080 } else { 8080 }
    if (-not $TestMode -and -not $CheckOnly) {
        $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
        if (-not $isAdmin) {
            Write-SetupLog 'Requesting standard Windows UAC elevation for installation.'
            $powershell = (Get-Command powershell.exe -ErrorAction Stop).Source
            $argumentList = '-NoLogo -NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $PSCommandPath.Replace('"','""')
            Start-Process -FilePath $powershell -Verb RunAs -ArgumentList ('-NoExit ' + $argumentList) | Out-Null
            exit 0
        }
    }
    Write-SetupLog '[1/8] Checking Windows, disk, permissions, ports, WSL2, and Docker.'
    if (-not (Start-DockerRequirements -Port $port)) { exit 3010 }
    if ($CheckOnly) {
        $failures = @($script:HostCheck.checks | Where-Object { $_.status -eq 'FAIL' })
        if ($failures.Count) { throw "Host preflight found $($failures.Count) failed requirement(s). Review host-requirements.json." }
        Write-Host 'HOST PREFLIGHT COMPLETE'; exit 0
    }

    $installState = $null
    if (Test-Path -LiteralPath $script:InstallStatePath) { try { $installState = Read-Json $script:InstallStatePath } catch { throw 'The existing installation marker is invalid. No database was changed.' } }
    if ($installState -and $installState.mode -eq 'portable' -and $installState.status -eq 'COMPLETE') {
        Write-SetupLog '[8/8] This portable installation is already complete. Running non-destructive verification only.'
        $existingProject = [string]$installState.composeProjectName
        $null = Invoke-PortableCompose -ProjectName $existingProject -Arguments @('up','-d')
        $existingBaseUrl = [string]$installState.baseUrl
        $existingReady = $false
        for ($i=0; $i -lt 60; $i++) {
            try { $ready = Invoke-RestMethod -Uri ($existingBaseUrl.TrimEnd('/') + '/health/ready') -TimeoutSec 3; if ($ready.status -eq 'ready') { $existingReady=$true; break } } catch { }
            Start-Sleep -Seconds 3
        }
        if (-not $existingReady) { throw 'The completed portable installation did not pass its readiness check; no database restore was repeated.' }
        Write-Host "PLATFORM SETUP COMPLETE`nURL: $($installState.baseUrl)" -ForegroundColor Green
        exit 0
    }
    if ((Test-Path -LiteralPath $script:EnvPath) -and -not (Test-Path -LiteralPath $script:ProgressPath)) {
        throw 'A local environment file already exists without a portable setup marker. To protect existing data and secrets, prepare and copy the clean portable-package folder rather than the source folder.'
    }
    $manifestPath = Join-Path $root 'transfer-manifest.json'
    $expectedPath = Join-Path $root 'expected-data-manifest.json'
    if (-not (Test-Path -LiteralPath $manifestPath) -or -not (Test-Path -LiteralPath $expectedPath)) { throw 'This folder is not a prepared transfer package. Run Prepare Transfer.bat on the source device and copy the resulting portable-package folder.' }
    $manifest = Read-Json $manifestPath
    if ($manifest.database_transfer_method -ne 'LOGICAL_BACKUP_RESTORE') { throw 'The package does not contain the required logical PostgreSQL backup format.' }
    if (Test-Path -LiteralPath (Join-Path $root 'Local Admin Credentials.txt')) { throw 'The package contains the source-machine plaintext Admin credential file. Remove it from the copy and retry; the restored user password is already stored in the database hash.' }
    Write-SetupLog '[4/8] Validating package files, database checksum, and encrypted session key.'
    $checkedFiles = Test-TransferChecksums -PackageRoot $root -Manifest $manifest
    Write-SetupLog "Validated $checkedFiles package checksum entries."
    $expectedDocument = Read-Json $expectedPath
    $expected = $expectedDocument.snapshot
    if ([int]$expected.active_admin_users -lt 1) { throw 'The transfer snapshot does not contain an active Admin user.' }
    if ([int]$expected.active_sync_jobs -ne 0) { throw 'The transfer snapshot reports active sync jobs. The source device must finish or explain them before transfer.' }

    if (-not $TransferPassphraseSecureString) { $TransferPassphraseSecureString = Read-Host 'أدخل عبارة مرور النقل لفك تشفير مفتاح الجلسات' -AsSecureString }
    $passphrase = ConvertTo-PortablePlainText $TransferPassphraseSecureString
    $sessionSecretPath = Join-Path $root 'transfer\private\session-signing-secret.aes'
    if (-not (Test-Path -LiteralPath $sessionSecretPath)) { throw 'The encrypted session-signing key is missing.' }
    $sessionSecret = Unprotect-PortableSecret -Path $sessionSecretPath -Passphrase $passphrase
    if ([string]::IsNullOrWhiteSpace($sessionSecret)) { throw 'The encrypted session-signing key could not be validated.' }
    [Array]::Clear($passphrase.ToCharArray(),0,$passphrase.Length)

    $progressState = $null
    if (Test-Path -LiteralPath $script:ProgressPath) { try { $progressState = Read-Json $script:ProgressPath } catch { throw 'The existing portable setup progress marker is invalid; the destination database was not changed.' } }
    $projectName = if ($installState -and $installState.composeProjectName) { [string]$installState.composeProjectName } elseif ($progressState -and $progressState.compose_project_name) { [string]$progressState.compose_project_name } else { if ($TestMode) { 'alahsa-transfer-test-' + [guid]::NewGuid().ToString('N').Substring(0,8) } else { 'alahsa-portable-' + [guid]::NewGuid().ToString('N').Substring(0,8) } }
    $network = if ($installState -and $installState.composeSubnet) { [pscustomobject]@{ subnet=[string]$installState.composeSubnet; frontendIp=([string]$installState.composeSubnet -replace '\.0/24$','.10') } } else { Select-FreeNetwork -ProjectName $projectName }
    if (-not (Test-Path -LiteralPath $script:ProgressPath)) {
        $progressDir = Split-Path -Parent $script:ProgressPath; New-Item -ItemType Directory -Path $progressDir -Force | Out-Null
        Save-Progress -Phase 'PACKAGE_VERIFIED' -ProjectName $projectName
        if (Test-Path -LiteralPath $script:EnvPath) { throw 'The destination already has environment configuration; refusing to replace it.' }
        Write-PortableEnvironment -SessionSecret $sessionSecret -ProjectName $projectName -Port $port -Subnet $network.subnet -FrontendIp $network.frontendIp
        Set-InstallationState -Phase 'INSTALLING' -ProjectName $projectName -Port $port -Subnet $network.subnet
    } elseif (-not (Test-Path -LiteralPath $script:EnvPath)) {
        throw 'Setup can resume only when its destination-specific private environment file is intact. No database restore was attempted.'
    }
    if (-not $TestMode -and $port -eq 8080) {
        $listener = Get-NetTCPConnection -State Listen -LocalPort 8080 -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($listener) { throw 'Port 8080 is occupied. No process was stopped. Free port 8080 and run Setup Platform.bat again.' }
    }
    $script:DockerPath = Find-DockerCli
    if (-not $script:DockerPath) { throw 'Docker CLI is unavailable after prerequisite checks.' }
    $projectName = if ($installState -and $installState.composeProjectName) { [string]$installState.composeProjectName } elseif ($progressState -and $progressState.compose_project_name) { [string]$progressState.compose_project_name } else { $projectName }
    $script:SetupLogEnabled = $true
    Write-SetupLog '[5/8] Preparing a fresh isolated PostgreSQL volume and Redis service.'
    $null = Invoke-PortableCompose -ProjectName $projectName -Arguments @('config','--quiet')
    $null = Invoke-PortableCompose -ProjectName $projectName -Arguments @('build','api','worker','scheduler','migrate','frontend')
    if (-not (Test-Path -LiteralPath $script:ProgressPath)) { throw 'The resumable setup stage file could not be written.' }
    $progress = Read-Json $script:ProgressPath
    $null = Invoke-PortableCompose -ProjectName $projectName -Arguments @('up','-d','db','redis')
    Wait-DatabaseRedis -ProjectName $projectName
    $schemaPresent = Get-DatabaseSchemaPresent -ProjectName $projectName
    if ($schemaPresent) {
        $existing = $null
        try { $existing = Get-PortableSnapshot -ProjectName $projectName } catch { $existing = $null }
        if ($existing -and (Test-ManifestSnapshot -Actual $existing -Expected $expected)) {
            Write-SetupLog 'An earlier run already restored the exact transfer snapshot; resuming without a second restore.'
            Save-Progress -Phase 'DATABASE_RESTORED' -ProjectName $projectName
        } elseif ($progress.phase -in @('RESTORE_STARTED','RESTORE_FAILED','DATABASE_RESTORED')) {
            Write-SetupLog 'An interrupted attempt left an incomplete isolated volume. Preserving it and moving this retry to a new Compose project name.'
            $null = Invoke-PortableCompose -ProjectName $projectName -Arguments @('stop','db','redis') -AllowFailure
            $oldProject = $projectName
            $projectName = if ($TestMode) { 'alahsa-transfer-test-' + [guid]::NewGuid().ToString('N').Substring(0,8) } else { 'alahsa-portable-' + [guid]::NewGuid().ToString('N').Substring(0,8) }
            $network = Select-FreeNetwork -ProjectName $projectName
            Write-PortableEnvironment -SessionSecret $sessionSecret -ProjectName $projectName -Port $port -Subnet $network.subnet -FrontendIp $network.frontendIp
            Set-InstallationState -Phase 'INSTALLING' -ProjectName $projectName -Port $port -Subnet $network.subnet
            Save-Progress -Phase 'PACKAGE_VERIFIED' -ProjectName $projectName
            Write-SetupLog "The previous isolated database was preserved under project $oldProject; it was not deleted."
            $null = Invoke-PortableCompose -ProjectName $projectName -Arguments @('up','-d','db','redis')
            Wait-DatabaseRedis -ProjectName $projectName
            $schemaPresent = Get-DatabaseSchemaPresent -ProjectName $projectName
        } else { throw 'The destination database is populated and does not match this transfer. Setup protected it and did not restore over it.' }
    }
    if (-not $schemaPresent) {
        if ($progress.phase -eq 'RESTORE_STARTED') { Save-Progress -Phase 'RESTORE_FAILED' -ProjectName $projectName }
        Save-Progress -Phase 'RESTORE_STARTED' -ProjectName $projectName
        Write-SetupLog '[6/8] Restoring the packaged PostgreSQL logical backup before starting API, Worker, Beat, or frontend.'
        $dumpPath = Join-Path $root ([string]$manifest.database_backup.path).Replace('/','\')
        $dbContainer = (Invoke-PortableCompose -ProjectName $projectName -Arguments @('ps','-q','db')).Trim()
        $containerDump = '/tmp/portable-transfer-' + [guid]::NewGuid().ToString('N') + '.dump'
        & $script:DockerPath 'cp' $dumpPath ($dbContainer + ':' + $containerDump) 2>&1 | Out-File -LiteralPath $logPath -Append -Encoding UTF8
        if ($LASTEXITCODE -ne 0) { Save-Progress -Phase 'RESTORE_FAILED' -ProjectName $projectName; throw 'The verified backup could not be copied to the isolated PostgreSQL container.' }
        $listCommand = 'pg_restore --list "' + $containerDump + '" >/dev/null'
        $null = Invoke-PortableCompose -ProjectName $projectName -Arguments @('exec','-T','db','sh','-lc',$listCommand) -AllowFailure
        $listExit = $script:LastComposeExit
        if ($listExit -ne 0) { $restoreExit = $listExit }
        else {
            $restoreCommand = 'pg_restore --exit-on-error --no-owner --no-acl --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" "' + $containerDump + '"'
            $null = Invoke-PortableCompose -ProjectName $projectName -Arguments @('exec','-T','db','sh','-lc',$restoreCommand) -AllowFailure
            $restoreExit = $script:LastComposeExit
        }
        $null = Invoke-PortableCompose -ProjectName $projectName -Arguments @('exec','-T','db','rm','-f',$containerDump) -AllowFailure
        if ($restoreExit -ne 0) { Save-Progress -Phase 'RESTORE_FAILED' -ProjectName $projectName; throw 'PostgreSQL restore failed. The partial destination volume was preserved; rerun Setup to continue in a fresh protected project.' }
        Save-Progress -Phase 'DATABASE_RESTORED' -ProjectName $projectName
    }
    Write-SetupLog 'Running Alembic upgrade after the database restore; this is idempotent and does not seed source records.'
    $null = Invoke-PortableCompose -ProjectName $projectName -Arguments @('run','--rm','--no-deps','migrate','alembic','upgrade','head')
    $restored = Get-PortableSnapshot -ProjectName $projectName
    if (-not (Test-ManifestSnapshot -Actual $restored -Expected $expected)) { throw 'Restored database counts, source configuration, users, review history, or merge lineage do not match the transfer manifest.' }
    if ([int]$restored.active_admin_users -lt 1) { throw 'The restored database does not contain an active Admin account.' }
    if ([int]$restored.active_sync_jobs -ne 0) { throw 'The transfer snapshot contains active sync jobs; scheduled services were not started.' }
    Write-SetupLog '[7/9] Starting only API and Worker so the restored runtime can publish its version heartbeat; Beat remains stopped.'
    $null = Invoke-PortableCompose -ProjectName $projectName -Arguments @('up','-d','api','worker')
    $workerReady = $false
    for ($attempt=0; $attempt -lt 30; $attempt++) {
        $ping = Invoke-PortableCompose -ProjectName $projectName -Arguments @('exec','-T','worker','celery','-A','app.celery_app:celery_app','inspect','ping') -AllowFailure
        if ($script:LastComposeExit -eq 0 -and $ping -match 'pong') { $workerReady = $true; break }
        Start-Sleep -Seconds 2
    }
    if (-not $workerReady) { throw 'The isolated Worker did not answer its readiness check; Beat and frontend were not started.' }
    $heartbeat = Invoke-PortableCompose -ProjectName $projectName -Arguments @('exec','-T','worker','python','scripts/portable_worker_heartbeat.py')
    if ($heartbeat.Trim() -ne 'HEARTBEAT_OK') { throw 'The isolated Worker did not publish its standardization version heartbeat; Beat and frontend were not started.' }
    Write-SetupLog '[8/9] Running read-only full DQ against the restored database before Beat starts.'
    $dq = Invoke-PortableCompose -ProjectName $projectName -Arguments @('run','--rm','--no-deps','-T','migrate','python','-m','scripts.run_data_quality','--scope','full') -AllowFailure
    $dqExit = $script:LastComposeExit
    $dqStart = $dq.IndexOf([char]123)
    if ($dqStart -lt 0) { throw 'The read-only transfer DQ check returned no JSON summary.' }
    $dqResult = $dq.Substring($dqStart) | ConvertFrom-Json
    $dqFail = [int]$dqResult.counts.fail
    $dqReportPath = Join-Path $root 'transfer-validation-dq.json'
    [IO.File]::WriteAllText($dqReportPath,([ordered]@{ scope='full'; counts=$dqResult.counts; gates_evaluated=$dqResult.gates_evaluated; persisted=$false; exit_code=$dqExit } | ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
    if ($dqFail -ne 0) { throw "The isolated restored database has $dqFail live DQ FAIL gate(s); Beat and normal services were not started." }
    Save-Progress -Phase 'PRE_START_VALIDATED' -ProjectName $projectName
    Set-InstallationState -Phase 'INSTALLING' -ProjectName $projectName -Port $port -Subnet $network.subnet
    Write-SetupLog '[9/9] Starting Beat and frontend only after restore, runtime parity, and DQ have passed.'
    $null = Invoke-PortableCompose -ProjectName $projectName -Arguments @('up','-d','scheduler','frontend')

    $baseUrl = "http://localhost:$port"
    $isReady = $false
    for ($i=0; $i -lt 120; $i++) {
        try {
            $live = Invoke-RestMethod -Uri ($baseUrl + '/health/live') -TimeoutSec 3
            $ready = Invoke-RestMethod -Uri ($baseUrl + '/health/ready') -TimeoutSec 3
            $front = Invoke-WebRequest -Uri ($baseUrl + '/') -UseBasicParsing -TimeoutSec 3
            if ($live.status -eq 'ok' -or $live.status -eq 'live') { }
            if ($ready.status -eq 'ready' -and $front.StatusCode -eq 200) { $isReady=$true; break }
        } catch { }
        Start-Sleep -Seconds 3
    }
    if (-not $isReady) { throw 'API readiness or frontend HTTP check failed after start. Database contents remain preserved; review the setup log.' }
    $ping = Invoke-PortableCompose -ProjectName $projectName -Arguments @('exec','-T','worker','celery','-A','app.celery_app:celery_app','inspect','ping') -AllowFailure
    if ($script:LastComposeExit -ne 0 -or $ping -notmatch 'pong') { throw 'The restored platform is ready but the Celery Worker did not answer its health check.' }
    $beat = Invoke-PortableCompose -ProjectName $projectName -Arguments @('logs','--no-color','--tail','80','scheduler') -AllowFailure
    if ($beat -notmatch 'celery beat|beat: Starting') { throw 'Celery Beat did not report a successful start.' }
    $noScheduleTest = $TestMode
    if ($noScheduleTest) {
        $settings = Invoke-PortableCompose -ProjectName $projectName -Arguments @('exec','-T','scheduler','python','-c','from app.celery_app import celery_app; print(len(celery_app.conf.beat_schedule))')
        if ($settings.Trim() -ne '0') { throw 'Transfer test Beat schedule was not disabled; the isolated source ingestion safety guard failed.' }
    }
    $final = Get-PortableSnapshot -ProjectName $projectName
    if ([int]$final.active_admin_users -lt 1) { throw 'The active Admin account is missing after services started.' }
    if ([int]$final.active_sync_jobs -ne 0) { throw 'Unexpected active sync jobs appeared during setup; inspect the isolated job state before proceeding.' }
    Set-InstallationState -Phase 'COMPLETE' -ProjectName $projectName -Port $port -Subnet $network.subnet
    Save-Progress -Phase 'COMPLETE' -ProjectName $projectName
    if (-not $TestMode) {
        try { & (Join-Path $root 'scripts\create-desktop-shortcuts.ps1') *> $null } catch { Write-SetupLog 'Desktop shortcuts were skipped; the Start/Stop/Status buttons remain available in this folder.' }
    }
    Write-SetupLog 'Platform transfer setup completed. No manual source sync was dispatched.'
    Write-Host '========================================' -ForegroundColor Green
    Write-Host 'PLATFORM SETUP COMPLETE' -ForegroundColor Green
    Write-Host 'المنصة جاهزة للعمل' -ForegroundColor Green
    Write-Host "URL: $baseUrl" -ForegroundColor Green
    Write-Host 'Transfer backup restored; source sync was not manually started.'
    if (-not $TestMode) { Start-Process $baseUrl }
    exit 0
} catch {
    Write-SetupLog "SETUP FAILED: $($_.Exception.Message)"
    Write-Host "`nSETUP FAILED`nFAILED STEP: $($_.Exception.Message)`nLog: $logPath" -ForegroundColor Red
    if (-not $TestMode -and -not $CheckOnly) { $null = Read-Host }
    exit 1
}
