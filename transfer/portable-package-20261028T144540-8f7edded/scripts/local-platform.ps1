$script:LocalProjectRoot = Split-Path -Parent $PSScriptRoot
$script:LocalConfigPath = Join-Path $script:LocalProjectRoot '.env.local'
$script:InstallationStatePath = Join-Path $script:LocalProjectRoot '.installation-state.json'
$script:InstallationState = $null
if (Test-Path -LiteralPath $script:InstallationStatePath) {
    try { $script:InstallationState = Get-Content -LiteralPath $script:InstallationStatePath -Raw | ConvertFrom-Json } catch { $script:InstallationState = $null }
}
$script:IsPortableInstallation = $script:InstallationState -and $script:InstallationState.mode -eq 'portable'
$script:LocalProjectName = if ($script:IsPortableInstallation -and $script:InstallationState.composeProjectName) { [string]$script:InstallationState.composeProjectName } else { 'alahsa-local' }
$localAppDataName = if ($script:IsPortableInstallation) { Join-Path 'Sharakat Data Base' $script:LocalProjectName } else { 'Sharakat Data Base' }
$script:LocalAppData = Join-Path $env:LOCALAPPDATA $localAppDataName
$script:LocalConfigBackup = Join-Path $script:LocalAppData '.env.local'
$script:LocalCredentialsPath = Join-Path $script:LocalProjectRoot 'Local Admin Credentials.txt'
$script:LocalCredentialsBackup = Join-Path $script:LocalAppData 'Local Admin Credentials.txt'
$script:LocalBaseUrl = if ($script:IsPortableInstallation -and $script:InstallationState.baseUrl) { [string]$script:InstallationState.baseUrl } else { 'http://localhost:8080' }
$script:PortableComposePath = Join-Path $script:LocalProjectRoot 'docker-compose.portable.yml'
$script:DockerPath = $null
$script:LogPath = $null

function Write-LocalLog([string]$Message) {
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $line = "[$stamp] $Message"
    Write-Host $Message
    if ($script:LogPath) { Add-Content -LiteralPath $script:LogPath -Value $line -Encoding UTF8 }
}

function Set-PrivateFile([string]$Path, [string]$Content) {
    $parent = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    [IO.File]::WriteAllText($Path, $Content, [Text.UTF8Encoding]::new($false))
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    & icacls.exe $Path '/inheritance:r' '/grant:r' "${identity}:(F)" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not restrict access to local private file: $(Split-Path -Leaf $Path)" }
}

function Find-DockerCli {
    $found = Get-Command docker -ErrorAction SilentlyContinue
    if ($found) { return $found.Source }
    $candidates = @(
        (Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin\docker.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe')
    )
    foreach ($candidate in $candidates) { if (Test-Path -LiteralPath $candidate) { return $candidate } }
    return $null
}

function Find-DockerDesktop {
    $candidates = @(
        (Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\Docker Desktop.exe')
    )
    foreach ($candidate in $candidates) { if (Test-Path -LiteralPath $candidate) { return $candidate } }
    return $null
}

function Ensure-DockerEngine([int]$TimeoutSeconds = 600) {
    $script:DockerPath = Find-DockerCli
    if (-not $script:DockerPath) {
        $desktop = Find-DockerDesktop
        if (-not $desktop) { throw 'Docker Desktop is not installed. Install Docker Desktop, start it once, then double-click Start Platform again.' }
        throw 'Docker Desktop is installed, but its Docker command line is missing. Repair Docker Desktop and try again.'
    }
    $dockerDirectory = Split-Path -Parent $script:DockerPath
    $pathEntries = @($env:PATH -split ';')
    if ($pathEntries -notcontains $dockerDirectory) { $env:PATH = "$dockerDirectory;$env:PATH" }
    $version = & $script:DockerPath '--version' 2>&1
    if ($LASTEXITCODE -ne 0) { throw 'Docker is installed but its command line did not start.' }
    $composeVersion = & $script:DockerPath 'compose' 'version' 2>&1
    if ($LASTEXITCODE -ne 0) { throw 'Docker Compose is unavailable. Update or repair Docker Desktop.' }
    Write-LocalLog "Docker detected: $version"

    $engineReady = $false
    try {
        & $script:DockerPath 'info' *> $null
        $engineReady = ($LASTEXITCODE -eq 0)
    } catch { $engineReady = $false }
    if (-not $engineReady) {
        $desktop = Find-DockerDesktop
        if ($desktop) {
            Write-LocalLog 'Starting Docker Desktop...'
            Start-Process -FilePath $desktop -WindowStyle Hidden | Out-Null
        }
        Write-LocalLog 'Waiting for Docker Engine...'
        for ($elapsed = 0; $elapsed -lt $TimeoutSeconds; $elapsed += 3) {
            Start-Sleep -Seconds 3
            try {
                & $script:DockerPath 'info' *> $null
                if ($LASTEXITCODE -eq 0) { $engineReady = $true; break }
            } catch { }
        }
    }
    if (-not $engineReady) { throw "Docker Engine did not become ready within $TimeoutSeconds seconds. Start Docker Desktop and retry." }
    Write-LocalLog 'Docker Engine is ready.'
}

function Get-ComposePrefix {
    if ($script:IsPortableInstallation) {
        return @('compose', '--env-file', '.env.local', '-f', 'docker-compose.yml', '-f', 'docker-compose.portable.yml', '-p', $script:LocalProjectName)
    }
    return @('compose', '--env-file', '.env.local', '-f', 'docker-compose.yml', '-f', 'docker-compose.local.yml', '-p', $script:LocalProjectName)
}

function Invoke-LocalCompose([string[]]$Arguments, [switch]$AllowFailure) {
    $dockerArgs = (Get-ComposePrefix) + $Arguments
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & $script:DockerPath @dockerArgs 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($output -and $script:LogPath) { $output | Out-File -LiteralPath $script:LogPath -Append -Encoding UTF8 }
    if ($exitCode -ne 0 -and -not $AllowFailure) { throw 'A local platform service command failed. See the log for details.' }
    return ($output -join [Environment]::NewLine)
}

function Get-LocalEnvValue([string]$Name) {
    $line = Get-Content -LiteralPath $script:LocalConfigPath | Where-Object { $_ -match "^$([regex]::Escape($Name))=" } | Select-Object -Last 1
    if (-not $line) { return '' }
    return $line.Substring($Name.Length + 1)
}

function Ensure-LocalConfig {
    if (Test-Path -LiteralPath $script:LocalConfigPath) {
        $content = [IO.File]::ReadAllText($script:LocalConfigPath)
        Set-PrivateFile -Path $script:LocalConfigPath -Content $content
        Set-PrivateFile -Path $script:LocalConfigBackup -Content $content
        if (-not (Test-Path -LiteralPath $script:LocalCredentialsPath) -and (Test-Path -LiteralPath $script:LocalCredentialsBackup)) {
            Set-PrivateFile -Path $script:LocalCredentialsPath -Content ([IO.File]::ReadAllText($script:LocalCredentialsBackup))
        }
        return
    }
    if (Test-Path -LiteralPath $script:LocalConfigBackup) {
        Set-PrivateFile -Path $script:LocalConfigPath -Content ([IO.File]::ReadAllText($script:LocalConfigBackup))
        if (-not (Test-Path -LiteralPath $script:LocalCredentialsPath) -and (Test-Path -LiteralPath $script:LocalCredentialsBackup)) {
            Set-PrivateFile -Path $script:LocalCredentialsPath -Content ([IO.File]::ReadAllText($script:LocalCredentialsBackup))
        }
        Write-LocalLog 'Restored private local settings from this Windows account.'
        return
    }
    $volumeExists = $false
    try {
        & $script:DockerPath 'volume' 'inspect' "$($script:LocalProjectName)_postgres_data" *> $null
        $volumeExists = ($LASTEXITCODE -eq 0)
    } catch { $volumeExists = $false }
    if ($volumeExists) {
        throw 'Local database storage already exists but its private settings file is missing. Startup stopped to protect your saved data.'
    }
    $password = ([guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N'))
    $redisPassword = ([guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N'))
    $secret = ([guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N'))
    $adminPassword = ([guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N'))
    $adminEmail = 'admin@local'
    $lines = @(
        'ENVIRONMENT=local_user',
        'POSTGRES_DB=sharakat_local',
        'POSTGRES_USER=sharakat_local',
        "POSTGRES_PASSWORD=$password",
        "DATABASE_URL=postgresql+psycopg://sharakat_local:$password@db:5432/sharakat_local",
        "REDIS_PASSWORD=$redisPassword",
        "REDIS_URL=redis://:$redisPassword@redis:6379/0",
        "SECRET_KEY=$secret",
        'PUBLIC_BASE_URL=http://localhost:8080',
        'CORS_ORIGINS=http://localhost:8080,http://127.0.0.1:8080',
        'FORWARDED_ALLOW_IPS=172.31.240.10',
        'COMPOSE_NETWORK_SUBNET=172.31.240.0/24',
        "BOOTSTRAP_ADMIN_EMAIL=$adminEmail",
        "BOOTSTRAP_ADMIN_PASSWORD=$adminPassword",
        'STAGING_DATABASE_NAME=sharakat_local',
        'BACKUP_DIR=/backups',
        'LOCAL_SQLITE_PATH=/source-data/al-ahsa-live.db',
        'LOCAL_EXPECTED_DATABASE=sharakat_local',
        'LOCAL_SETUP_MARKER=local_setup_state'
    )
    $content = ($lines -join "`r`n") + "`r`n"
    Set-PrivateFile -Path $script:LocalConfigPath -Content $content
    Set-PrivateFile -Path $script:LocalConfigBackup -Content $content
    $credentials = @"
Al-Ahsa Investment Platform – Local Admin

Email: $adminEmail
Password: $adminPassword

This password was generated for this computer. Keep this file private.
"@
    Set-PrivateFile -Path $script:LocalCredentialsPath -Content $credentials
    Set-PrivateFile -Path $script:LocalCredentialsBackup -Content $credentials
    Write-LocalLog 'Created private local settings and a first-run Admin login for this computer.'
}

function Initialize-LocalLogging([string]$Name) {
    $logDir = Join-Path $script:LocalProjectRoot 'logs'
    if (-not (Test-Path -LiteralPath $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
    $script:LogPath = Join-Path $logDir $Name
    Add-Content -LiteralPath $script:LogPath -Value "`r`n--- $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ---" -Encoding UTF8
}

