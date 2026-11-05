$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'local-platform.ps1')
Set-Location -LiteralPath $script:LocalProjectRoot
Initialize-LocalLogging 'startup.log'

try {
    Write-Host '========================================'
    Write-Host 'Al-Ahsa Investment Platform'
    Write-Host '========================================'
    Write-LocalLog '[1/7] Checking project files and local data...'
    foreach ($path in @('docker-compose.yml','docker-compose.local.yml','Dockerfile','frontend.Dockerfile','data\al-ahsa-live.db')) {
        if (-not (Test-Path -LiteralPath (Join-Path $script:LocalProjectRoot $path))) { throw "Required local project file is missing: $path. Startup stopped without creating an empty database." }
    }
    Write-LocalLog '[2/7] Checking Docker Desktop...'
    Ensure-DockerEngine
    Ensure-LocalConfig
    $composeValidation = Invoke-LocalCompose -Arguments @('config','--quiet')

    $runningFrontend = Invoke-LocalCompose -Arguments @('ps','-q','frontend') -AllowFailure
    if ($runningFrontend.Trim()) {
        try {
            $ready = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/health/ready' -TimeoutSec 3
            $front = Invoke-WebRequest -Uri 'http://127.0.0.1:8080/' -UseBasicParsing -TimeoutSec 3
            if ($ready.status -eq 'ready' -and $front.StatusCode -eq 200) {
                Write-LocalLog 'Platform is already running; opening the browser.'
                Start-Process 'http://localhost:8080'
                exit 0
            }
        } catch { }
    }

    $listener = Get-NetTCPConnection -State Listen -LocalPort 8080 -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener -and -not $runningFrontend.Trim()) { throw 'Port 8080 is being used by another application. Close it, then try Start Platform again.' }

    Write-LocalLog '[3/7] Starting PostgreSQL and Redis...'
    Write-LocalLog '[4/7] Checking database and preserving existing SQLite data...'
    Write-LocalLog '[5/7] Applying migrations and starting API, worker, scheduler, and frontend...'
    $null = Invoke-LocalCompose -Arguments @('up','-d','--build')
    $heads = Invoke-LocalCompose -Arguments @('run','--rm','--no-deps','migrate','alembic','heads') -AllowFailure
    $headsExit = $LASTEXITCODE
    $migration = Invoke-LocalCompose -Arguments @('run','--rm','--no-deps','migrate','alembic','current') -AllowFailure
    $migrationExit = $LASTEXITCODE
    $expectedRevisions = @([regex]::Matches($heads, '(?m)^([A-Za-z0-9_]+)\s+\(head\)\s*$') | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique)
    $currentRevisions = @([regex]::Matches($migration, '(?m)^([A-Za-z0-9_]+)(?:\s+\(head\))?\s*$') | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique)
    if ($headsExit -ne 0 -or $migrationExit -ne 0 -or -not $expectedRevisions.Count -or ($expectedRevisions -join '|') -ne ($currentRevisions -join '|')) {
        throw 'The local database migration is not at every Alembic head defined by this project.'
    }

    Write-LocalLog '[6/7] Waiting for database, Redis, worker, scheduler, and frontend readiness...'
    $ready = $false
    for ($attempt = 0; $attempt -lt 100; $attempt++) {
        try {
            $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/health/ready' -TimeoutSec 3
            $front = Invoke-WebRequest -Uri 'http://127.0.0.1:8080/' -UseBasicParsing -TimeoutSec 3
            $worker = Invoke-LocalCompose -Arguments @('exec','-T','worker','celery','-A','app.celery_app:celery_app','inspect','ping') -AllowFailure
            if ($health.status -eq 'ready' -and $front.StatusCode -eq 200 -and $worker -match 'pong') { $ready = $true; break }
        } catch { }
        Start-Sleep -Seconds 3
    }
    if (-not $ready) { throw 'The platform did not become fully ready within five minutes. Check service logs.' }
    $beatLogs = Invoke-LocalCompose -Arguments @('logs','--no-color','--tail','80','scheduler') -AllowFailure
    if ($beatLogs -notmatch 'celery beat|beat: Starting|Scheduler: Sending due task') { throw 'Celery Beat did not report that it started. Check the scheduler logs.' }

    Write-LocalLog '[7/7] Platform is ready.'
    Write-LocalLog 'Opening http://localhost:8080'
    Start-Process 'http://localhost:8080'
    Start-Sleep -Seconds 2
} catch {
    Write-LocalLog "Platform failed to start: $($_.Exception.Message)"
    Write-Host "`nPlatform failed to start. Detailed log: logs\startup.log" -ForegroundColor Red
    Read-Host 'Press Enter to close this window'
    exit 1
}
