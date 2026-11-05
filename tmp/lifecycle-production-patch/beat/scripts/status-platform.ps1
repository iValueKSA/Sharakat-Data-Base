$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'local-platform.ps1')
Set-Location -LiteralPath $script:LocalProjectRoot

function Write-ServiceState([string]$Label, [string]$State) {
    Write-Host ('{0,-12} {1}' -f ($Label + ':'), $State)
}

try {
    $script:DockerPath = Find-DockerCli
    if (-not $script:DockerPath) {
        Write-ServiceState 'Docker' 'UNHEALTHY (not installed)'
        foreach ($service in @('PostgreSQL','Redis','API','Frontend','Worker','Scheduler')) {
            Write-ServiceState $service 'STOPPED'
        }
        Read-Host 'Press Enter to close'
        exit 1
    }

    $dockerDirectory = Split-Path -Parent $script:DockerPath
    if (($env:PATH -split ';') -notcontains $dockerDirectory) { $env:PATH = "$dockerDirectory;$env:PATH" }
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $script:DockerPath 'info' *> $null
        $engineReady = ($LASTEXITCODE -eq 0)
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    if (-not $engineReady) {
        Write-ServiceState 'Docker' 'STOPPED'
        foreach ($service in @('PostgreSQL','Redis','API','Frontend','Worker','Scheduler')) {
            Write-ServiceState $service 'STOPPED'
        }
        Read-Host 'Press Enter to close'
        exit 0
    }

    Write-ServiceState 'Docker' 'RUNNING'
    if (-not (Test-Path -LiteralPath $script:LocalConfigPath) -and (Test-Path -LiteralPath $script:LocalConfigBackup)) {
        Ensure-LocalConfig
    }
    if (-not (Test-Path -LiteralPath $script:LocalConfigPath)) {
        foreach ($service in @('PostgreSQL','Redis','API','Frontend','Worker','Scheduler')) {
            Write-ServiceState $service 'STOPPED'
        }
        Write-Host 'Local platform has not been configured yet.'
        Read-Host 'Press Enter to close'
        exit 0
    }

    $raw = Invoke-LocalCompose -Arguments @('ps','--all','--format','{{json .}}') -AllowFailure
    $states = @{}
    foreach ($line in ($raw -split "`r?`n" | Where-Object { $_.Trim() })) {
        try {
            $item = $line | ConvertFrom-Json
            $states[$item.Service] = if ($item.State -match 'running|up') {
                if ($item.Health -eq 'unhealthy') { 'UNHEALTHY' } else { 'RUNNING' }
            } else { 'STOPPED' }
        } catch { }
    }

    foreach ($mapping in @(
        @{ Service='db'; Label='PostgreSQL' },
        @{ Service='redis'; Label='Redis' },
        @{ Service='api'; Label='API' },
        @{ Service='frontend'; Label='Frontend' },
        @{ Service='worker'; Label='Worker' },
        @{ Service='scheduler'; Label='Scheduler' }
    )) {
        $state = if ($states.ContainsKey($mapping.Service)) { $states[$mapping.Service] } else { 'STOPPED' }
        Write-ServiceState $mapping.Label $state
    }

    try {
        $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/health/ready' -TimeoutSec 3
        Write-ServiceState 'Readiness' $(if ($health.status -eq 'ready') { 'RUNNING' } else { 'UNHEALTHY' })
    } catch {
        Write-ServiceState 'Readiness' 'UNHEALTHY'
    }
    Read-Host 'Press Enter to close'
} catch {
    Write-Host "Could not read platform status: $($_.Exception.Message)" -ForegroundColor Red
    Read-Host 'Press Enter to close'
    exit 1
}
