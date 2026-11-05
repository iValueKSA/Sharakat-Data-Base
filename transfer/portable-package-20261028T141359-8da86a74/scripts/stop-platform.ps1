$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'local-platform.ps1')
Set-Location -LiteralPath $script:LocalProjectRoot
Initialize-LocalLogging 'shutdown.log'
try {
    Write-LocalLog 'Stopping the local platform...'
    $script:DockerPath = Find-DockerCli
    if (-not $script:DockerPath) { throw 'Docker Desktop is not available. Start Docker Desktop, then retry Stop Platform.' }
    & $script:DockerPath 'info' *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-LocalLog 'Docker Engine is stopped; no running platform containers were changed.'
        exit 0
    }
    if (-not (Test-Path -LiteralPath $script:LocalConfigPath) -and -not (Test-Path -LiteralPath $script:LocalConfigBackup)) {
        Write-LocalLog 'Local platform has not been configured; nothing to stop.'
        exit 0
    }
    Ensure-LocalConfig
    $stopOutput = Invoke-LocalCompose -Arguments @('stop') -AllowFailure
    $remaining = $null
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        $remaining = & $script:DockerPath 'ps' '--filter' 'label=com.docker.compose.project=alahsa-local' '--filter' 'status=running' '--format' '{{.ID}}' 2>$null
        if ($LASTEXITCODE -eq 0 -and -not $remaining) { break }
        Start-Sleep -Seconds 1
    }
    if ($remaining) {
        throw 'One or more platform services are still running after the stop request.'
    }
    Write-LocalLog 'Platform stopped successfully. All services are stopped and your data has been preserved.'
} catch {
    Write-LocalLog "Platform could not be stopped: $($_.Exception.Message)"
    Write-Host 'See logs\shutdown.log for details.' -ForegroundColor Red
    Read-Host 'Press Enter to close this window'
    exit 1
}
