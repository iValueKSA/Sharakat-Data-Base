param(
    [switch]$TestMode,
    [Security.SecureString]$TransferPassphraseSecureString
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = Split-Path -Parent $PSCommandPath
$logDir = Join-Path $root 'logs'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$transferLogPath = Join-Path $logDir 'portable-transfer.log'
. (Join-Path $root 'scripts\portable-crypto.ps1')
. (Join-Path $root 'scripts\local-platform.ps1')

function Write-TransferLog([string]$Message) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
    Write-Host $Message
    Add-Content -LiteralPath $transferLogPath -Value $line -Encoding UTF8
}

function Find-DockerCli {
    $command = Get-Command docker.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command) { return $command.Source }
    $candidates = @((Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin\docker.exe'),(Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'))
    return ($candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1)
}

function Invoke-LiveCompose([string[]]$Arguments) {
    $docker = $script:DockerPath
    $prefix = Get-ComposePrefix
    $output = & $docker @($prefix + $Arguments) 2>&1
    $code = $LASTEXITCODE
    if ($output) { $output | Out-File -LiteralPath $transferLogPath -Append -Encoding UTF8 }
    if ($code -ne 0) { throw "A read-only transfer preparation command failed (exit $code). See the transfer log." }
    return ($output -join [Environment]::NewLine)
}

function Get-LiveSnapshot {
    $raw = Invoke-LiveCompose -Arguments @('run','--rm','--no-deps','migrate','python','scripts/portable_transfer_snapshot.py')
    $line = @($raw -split "`r?`n" | Where-Object { $_.Trim().StartsWith('{') } | Select-Object -Last 1)
    if (-not $line) { throw 'The read-only database snapshot did not return a manifest.' }
    return ($line[0] | ConvertFrom-Json)
}

function Get-SecretEnvValue([string]$Name) {
    $match = Get-Content -LiteralPath (Join-Path $root '.env.local') | Where-Object { $_ -match "^$([regex]::Escape($Name))=" } | Select-Object -Last 1
    if (-not $match) { throw "Required private setting $Name is missing; its value was not printed." }
    return $match.Substring($Name.Length + 1)
}

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-PortableFileList([string]$Base) {
    $files = [System.Collections.Generic.List[string]]::new()
    $critical = @('docker-compose.yml','docker-compose.local.yml','docker-compose.portable.yml','Dockerfile','frontend.Dockerfile','deploy\nginx.conf','requirements.txt','alembic.ini','PORTABLE-SETUP-README.md','Setup Platform.bat','Setup Platform.ps1','Verify Installation.bat','Check New PC.bat','Prepare Transfer.bat','Prepare Transfer.ps1')
    foreach ($relative in $critical) {
        $path = Join-Path $Base $relative
        if (Test-Path -LiteralPath $path -PathType Leaf) { $files.Add(($relative -replace '\\','/')) }
    }
    foreach ($directory in @('app','migrations','scripts','deploy','tests','docs/validation/deployment/portable-transfer')) {
        $path = Join-Path $Base $directory
        if (Test-Path -LiteralPath $path) {
            Get-ChildItem -LiteralPath $path -File -Recurse | Where-Object {
                $_.Extension -ne '.pyc' -and
                $_.FullName -notmatch '[\\/](__pycache__|node_modules|\.pytest_cache|\.ruff_cache)[\\/]' -and
                $_.Name -ne 'host-requirements.json'
            } | ForEach-Object {
                $files.Add($_.FullName.Substring($Base.TrimEnd('\').Length + 1).Replace('\','/'))
            }
        }
    }
    return @($files | Sort-Object -Unique)
}

try {
    Set-Location -LiteralPath $root
    Write-TransferLog 'Checking source platform readiness without changing its data.'
    if (-not (Test-Path -LiteralPath '.env.local')) { throw 'The existing private .env.local settings file is missing; no replacement was generated.' }
    $script:DockerPath = Find-DockerCli
    if (-not $script:DockerPath) { throw 'Docker CLI was not found. Install Docker Desktop before preparing the transfer.' }
    & $script:DockerPath info *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Docker Engine is not running. Start Docker Desktop and retry.' }
    $ready = Invoke-RestMethod -Uri ($script:LocalBaseUrl.TrimEnd('/') + '/health/ready') -TimeoutSec 5
    $front = Invoke-WebRequest -Uri ($script:LocalBaseUrl.TrimEnd('/') + '/') -UseBasicParsing -TimeoutSec 5
    if ($ready.status -ne 'ready' -or $front.StatusCode -ne 200) { throw 'The existing platform is not fully ready; no database backup was started.' }
    Write-TransferLog 'Building the read-only snapshot helper image; live containers are not restarted.'
    $null = Invoke-LiveCompose -Arguments @('build','migrate')
    $before = Get-LiveSnapshot
    if ([int]$before.active_sync_jobs -ne 0) { throw "Transfer paused because the live database reports $($before.active_sync_jobs) active sync jobs. Let the current work finish and try again." }
    if ([int]$before.active_admin_users -lt 1) { throw 'The live database has no active Admin account; transfer stopped before creating a backup.' }

    $runId = (Get-Date -Format 'yyyyMMddTHHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)
    $transferRoot = Join-Path $root 'transfer'
    $runRoot = Join-Path $transferRoot $runId
    $databaseDir = Join-Path $runRoot 'database'
    $privateDir = Join-Path $runRoot 'private'
    $packageRoot = Join-Path $transferRoot ('portable-package-' + $runId)
    New-Item -ItemType Directory -Path $databaseDir,$privateDir,$packageRoot -Force | Out-Null
    $backupName = 'al-ahsa-platform-' + $runId + '.dump'
    $backupPath = Join-Path $databaseDir $backupName
    $containerDump = '/tmp/' + $backupName
    Write-TransferLog 'Creating a fresh PostgreSQL custom-format logical backup.'
    $null = Invoke-LiveCompose -Arguments @('exec','-T','db','sh','-lc',('pg_dump --format=custom --no-owner --no-acl --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --file="' + $containerDump + '"'))
    $null = Invoke-LiveCompose -Arguments @('exec','-T','db','sh','-lc',('pg_restore --list "' + $containerDump + '" >/dev/null'))
    $dbContainer = (Invoke-LiveCompose -Arguments @('ps','-q','db')).Trim()
    if (-not $dbContainer) { throw 'The PostgreSQL container identifier could not be read.' }
    & $script:DockerPath 'cp' ($dbContainer + ':' + $containerDump) $backupPath 2>&1 | Out-File -LiteralPath $transferLogPath -Append -Encoding UTF8
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $backupPath) -or (Get-Item -LiteralPath $backupPath).Length -lt 1024) { throw 'The PostgreSQL logical backup could not be copied or is unexpectedly small.' }
    $null = Invoke-LiveCompose -Arguments @('exec','-T','db','rm','-f',$containerDump)
    $backupHash = Get-Sha256 $backupPath
    Write-TransferLog 'Validating that business-state counts remained stable while the consistent database snapshot was created.'
    $after = Get-LiveSnapshot
    $beforeJson = $before | ConvertTo-Json -Depth 8 -Compress
    $afterJson = $after | ConvertTo-Json -Depth 8 -Compress
    if ($beforeJson -cne $afterJson) { throw 'Live counts or transfer fingerprints changed during backup. The backup remains isolated in its timestamped folder; rerun during a quiet interval.' }

    if (-not $TransferPassphraseSecureString) {
        $first = Read-Host 'أنشئ عبارة مرور خاصة بحزمة النقل (لن تُسجل أو تُكتب في التقرير)' -AsSecureString
        $second = Read-Host 'أعد إدخال عبارة المرور للتأكيد' -AsSecureString
        $pass1 = ConvertTo-PortablePlainText $first; $pass2 = ConvertTo-PortablePlainText $second
        if ($pass1 -cne $pass2 -or $pass1.Length -lt 16) { throw 'The transfer passphrases did not match or were shorter than 16 characters.' }
        $TransferPassphraseSecureString = $first
    }
    $passphrase = ConvertTo-PortablePlainText $TransferPassphraseSecureString
    if ($passphrase.Length -lt 16) { throw 'The transfer passphrase must contain at least 16 characters.' }
    Protect-PortableSecret -Value (Get-SecretEnvValue 'SECRET_KEY') -Passphrase $passphrase -Path (Join-Path $privateDir 'session-signing-secret.aes')
    [Array]::Clear($passphrase.ToCharArray(),0,$passphrase.Length)

    $expected = [ordered]@{ schema_version = 1; created_at_utc = (Get-Date).ToUniversalTime().ToString('o'); snapshot = $after }
    $expectedPath = Join-Path $runRoot 'expected-data-manifest.json'
    [IO.File]::WriteAllText($expectedPath,($expected | ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
    $staticDir = Join-Path $root 'app\static'
    $requiredStatic = @('media\ahsa-investment-hero-poster.webp','media\ahsa-investment-hero.webm','brand\ahda-logo-inverse.svg','geo\alahsa-governorate.geojson')
    $missing = @($requiredStatic | Where-Object { -not (Test-Path -LiteralPath (Join-Path $staticDir $_) -PathType Leaf) })
    if ($missing.Count) { throw 'One or more required application-owned static assets are missing; no package was declared ready.' }
    $tlsPath = Join-Path $root 'app\certificates\mwan-digicert-global-g2-tls-rsa-sha256-2020-ca1.pem'
    if (-not (Test-Path -LiteralPath $tlsPath -PathType Leaf)) { throw 'The pinned MWAN TLS issuer certificate is missing.' }

    Write-TransferLog 'Copying the project into a clean, self-contained portable folder (excluding host secrets, stale SQLite, old backups, logs, and caches).'
    $excludeDirs = @((Join-Path $root '.git'),(Join-Path $root '.local-setup'),(Join-Path $root '.pytest_cache'),(Join-Path $root '.ruff_cache'),(Join-Path $root '.venv'),(Join-Path $root 'backups'),(Join-Path $root 'data'),(Join-Path $root 'logs'),(Join-Path $root 'node_modules'),(Join-Path $root 'tmp'),(Join-Path $root 'transfer'))
    $excludeFiles = @('.env.local','Local Admin Credentials.txt','*.pyc','*.log')
    $robocopyArgs = @($root,$packageRoot,'/E','/COPY:DAT','/DCOPY:DAT','/R:1','/W:1','/NFL','/NDL','/NJH','/NJS','/NP','/XF') + $excludeFiles + @('/XD') + $excludeDirs
    & robocopy.exe @robocopyArgs *> $null
    if ($LASTEXITCODE -ge 8) { throw 'Copying the portable project files failed. The source project was not modified.' }
    $packageTransferRoot = Join-Path $packageRoot 'transfer'
    $packageDatabaseDir = Join-Path $packageTransferRoot 'database'
    $packagePrivateDir = Join-Path $packageTransferRoot 'private'
    [void][IO.Directory]::CreateDirectory($packageDatabaseDir)
    [void][IO.Directory]::CreateDirectory($packagePrivateDir)
    Copy-Item -LiteralPath $backupPath -Destination (Join-Path $packageDatabaseDir $backupName)
    Copy-Item -LiteralPath $expectedPath -Destination (Join-Path $packageRoot 'expected-data-manifest.json')
    Copy-Item -LiteralPath (Join-Path $privateDir 'session-signing-secret.aes') -Destination (Join-Path $packagePrivateDir 'session-signing-secret.aes')
    if ((Test-Path -LiteralPath (Join-Path $packageRoot '.env.local')) -or (Test-Path -LiteralPath (Join-Path $packageRoot 'Local Admin Credentials.txt'))) { throw 'The portable folder unexpectedly contains a source-machine credential file.' }

    $assetFiles = @(Get-ChildItem -LiteralPath $staticDir -File -Recurse | Where-Object { $_.Extension -ne '.pyc' })
    $manifestFiles = [System.Collections.Generic.List[object]]::new()
    foreach ($relative in (Get-PortableFileList $packageRoot)) {
        $path = Join-Path $packageRoot ($relative -replace '/','\')
        if (Test-Path -LiteralPath $path -PathType Leaf) { $manifestFiles.Add([ordered]@{ path=$relative; size_bytes=(Get-Item -LiteralPath $path).Length; sha256=(Get-Sha256 $path) }) }
    }
    foreach ($relative in @('expected-data-manifest.json',('transfer\database\' + $backupName),'transfer\private\session-signing-secret.aes')) {
        $path = Join-Path $packageRoot $relative
        $manifestFiles.Add([ordered]@{ path=($relative -replace '\\','/'); size_bytes=(Get-Item -LiteralPath $path).Length; sha256=(Get-Sha256 $path); sensitive=($relative -match 'database|private') })
    }
    $version = [ordered]@{ setup_version='1.0.0'; package_id=$runId; created_at_utc=(Get-Date).ToUniversalTime().ToString('o'); alembic_heads=$after.alembic_heads }
    foreach ($base in @($packageRoot,$runRoot)) {
        $versionPath = Join-Path $base 'portable-setup-version.json'
        [IO.File]::WriteAllText($versionPath,($version | ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
    }
    $versionPath = Join-Path $packageRoot 'portable-setup-version.json'
    $manifestFiles.Add([ordered]@{ path='portable-setup-version.json'; size_bytes=(Get-Item -LiteralPath $versionPath).Length; sha256=(Get-Sha256 $versionPath) })
    $manifest = [ordered]@{
        schema_version = 1; setup_version = '1.0.0'; package_id = $runId; created_at_utc = (Get-Date).ToUniversalTime().ToString('o')
        package_root = '.'; database_transfer_method = 'LOGICAL_BACKUP_RESTORE'; database_backup = [ordered]@{ path=('transfer/database/'+$backupName); format='PostgreSQL custom'; sha256=$backupHash; validated_with='pg_restore --list'; contains_business_data_and_password_hashes=$true }
        expected_data_manifest = 'expected-data-manifest.json'; encrypted_secret_bundle = [ordered]@{ path='transfer/private/session-signing-secret.aes'; content='session signing key only'; encrypted=$true; plaintext_secrets_in_manifest=$false }
        excluded_source_machine_secrets = @('.env.local','Local Admin Credentials.txt'); excluded_runtime_data = @('data/','backups/','logs/','tmp/','node_modules/','__pycache__/')
        source_snapshot = $after; static_asset_count = $assetFiles.Count; static_asset_total_bytes = (($assetFiles | Measure-Object -Property Length -Sum).Sum); required_static_assets = $requiredStatic; mwAN_tls = [ordered]@{ path='app/certificates/mwan-digicert-global-g2-tls-rsa-sha256-2020-ca1.pem'; sha256=(Get-Sha256 $tlsPath); strict_verification_preserved=$true }
        files = @($manifestFiles.ToArray()); secrets_printed_to_console=$false; secrets_written_to_validation_report=$false
    }
    $manifestText = $manifest | ConvertTo-Json -Depth 10
    [IO.File]::WriteAllText((Join-Path $packageRoot 'transfer-manifest.json'),$manifestText,[Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText((Join-Path $runRoot 'transfer-manifest.json'),$manifestText,[Text.UTF8Encoding]::new($false))
    $checksumLines = foreach ($file in $manifestFiles) { "$($file.sha256)  $($file.path)" }
    $checksumText = ($checksumLines -join "`n") + "`n"
    [IO.File]::WriteAllText((Join-Path $packageRoot 'checksums.sha256'),$checksumText,[Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText((Join-Path $runRoot 'checksums.sha256'),$checksumText,[Text.UTF8Encoding]::new($false))

    Write-TransferLog "Database backup SHA-256: $backupHash"
    Write-TransferLog '========================================'
    Write-TransferLog 'TRANSFER PACKAGE READY'
    Write-TransferLog "Package folder: transfer\portable-package-$runId"
    Write-TransferLog 'يمكنك الآن نسخ مجلد الحزمة portable-package إلى الجهاز الجديد.'
    Write-TransferLog 'The package is ready. The source platform and database were not restarted or modified.'
    Write-Host '========================================' -ForegroundColor Green
    Write-Host 'TRANSFER PACKAGE READY' -ForegroundColor Green
    Write-Host 'يمكنك الآن نسخ مجلد الحزمة portable-package إلى الجهاز الجديد.' -ForegroundColor Green
    Write-Host "Package: $packageRoot"
    Write-Host "Database SHA-256: $backupHash"
    if (-not $TestMode) { Read-Host 'Press Enter to close' | Out-Null }
    exit 0
} catch {
    $failureLine = $_.InvocationInfo.ScriptLineNumber
    Write-TransferLog "TRANSFER PREPARATION FAILED at line $failureLine`: $($_.Exception.Message)"
    Write-Host "`nTRANSFER PREPARATION FAILED at line $failureLine`n$($_.Exception.Message)`nLog: $transferLogPath" -ForegroundColor Red
    if (-not $TestMode) { Read-Host 'Press Enter to close' | Out-Null }
    exit 1
}
