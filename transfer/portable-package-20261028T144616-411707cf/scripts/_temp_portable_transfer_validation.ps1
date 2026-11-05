$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
$bytes = New-Object byte[] 32
$rng = [Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes)
$phrase = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','-').Replace('/','_')
[Array]::Clear($bytes,0,$bytes.Length)
$pass = ConvertTo-SecureString $phrase -AsPlainText -Force
$phrase = $null
$rng.Dispose()
try {
    Write-Output 'PREPARE_STAGE'
    $prepareStarted = Get-Date
    $job = Start-Job -ArgumentList $pass,$root -ScriptBlock {
        param($transferPass,$projectRoot)
        Set-Location -LiteralPath $projectRoot
        & (Join-Path $projectRoot 'Prepare Transfer.ps1') -TestMode -TransferPassphraseSecureString $transferPass
    }
    $null = Wait-Job $job
    $prepareOutput = @(Receive-Job $job 2>&1)
    $prepareState = $job.State
    $prepareText = $prepareOutput | Out-String
    $prepareOutput | Select-Object -Last 5 | ForEach-Object { [string]$_ }
    Remove-Job $job
    $package = Get-ChildItem -LiteralPath (Join-Path $root 'transfer') -Directory -Filter 'portable-package-*' | Where-Object { $_.CreationTime -ge $prepareStarted.AddSeconds(-2) } | Sort-Object CreationTimeUtc | Select-Object -Last 1
    if (-not $package -or -not (Test-Path -LiteralPath (Join-Path $package.FullName 'transfer-manifest.json'))) { throw 'Final transfer manifest is missing.' }
    $testRoot = Join-Path $env:TEMP ('AlAhsa-Portable-Transfer-Final-' + [guid]::NewGuid().ToString('N').Substring(0,8))
    $null = New-Item -ItemType Directory -Path $testRoot
    & robocopy.exe $package.FullName $testRoot /E /COPY:DAT /DCOPY:DAT /R:1 /W:1 /NFL /NDL /NJH /NJS /NP *> $null
    $copyExit = $LASTEXITCODE
    if ($copyExit -ge 8) { throw 'Isolated package copy failed.' }

    Write-Output 'SETUP_STAGE_WINDOWS_POWERSHELL_5_1'
    $job = Start-Job -ArgumentList $pass,$testRoot -ScriptBlock {
        param($transferPass,$projectRoot)
        Set-Location -LiteralPath $projectRoot
        & (Join-Path $projectRoot 'Setup Platform.ps1') -TestMode -TransferPassphraseSecureString $transferPass
    }
    $null = Wait-Job $job
    $setupOutput = @(Receive-Job $job 2>&1)
    $setupState = $job.State
    $setupText = $setupOutput | Out-String
    $setupOk = $setupText -match 'PLATFORM SETUP COMPLETE'
    $setupOutput | Select-Object -Last 14 | ForEach-Object { [string]$_ }
    Remove-Job $job
    if (-not $setupOk) { throw "Setup did not complete under Windows PowerShell 5.1; job state=$setupState" }

    $install = Get-Content -LiteralPath (Join-Path $testRoot '.installation-state.json') -Raw | ConvertFrom-Json
    $prefix = @('--env-file',(Join-Path $testRoot '.env.local'),'-p',$install.composeProjectName,'-f',(Join-Path $testRoot 'docker-compose.yml'),'-f',(Join-Path $testRoot 'docker-compose.portable.yml'))
    function Get-TestSnapshot([string[]]$ComposePrefix) {
        $previous = $ErrorActionPreference
        try { $ErrorActionPreference = 'Continue'; $raw = & docker compose @ComposePrefix run --rm --no-deps -T migrate python scripts/portable_transfer_snapshot.py 2>&1; $exitCode = $LASTEXITCODE }
        finally { $ErrorActionPreference = $previous }
        if ($exitCode -ne 0) { throw 'The isolated snapshot query failed.' }
        $json = @($raw | ForEach-Object { [string]$_ } | Where-Object { $_.Trim().StartsWith('{') } | Select-Object -Last 1)
        if (-not $json) { throw 'The isolated snapshot JSON is missing.' }
        return ($json[0] | ConvertFrom-Json)
    }
    $before = Get-TestSnapshot $prefix
    $volumeBefore = @(& docker volume ls -q --filter "name=$($install.composeProjectName)_postgres_data")
    $progressPath = Join-Path $testRoot 'transfer/.portable-setup-state.json'
    $progressHashBefore = (Get-FileHash -LiteralPath $progressPath -Algorithm SHA256).Hash
    $job = Start-Job -ArgumentList $testRoot -ScriptBlock {
        param($projectRoot)
        Set-Location -LiteralPath $projectRoot
        & (Join-Path $projectRoot 'Setup Platform.ps1') -TestMode
    }
    $null = Wait-Job $job
    $idempotentOutput = @(Receive-Job $job 2>&1)
    $idempotentText = $idempotentOutput | Out-String
    $idempotent = $idempotentText -match 'already complete|PLATFORM SETUP COMPLETE'
    Remove-Job $job
    $after = Get-TestSnapshot $prefix
    $volumeAfter = @(& docker volume ls -q --filter "name=$($install.composeProjectName)_postgres_data")
    $progressHashAfter = (Get-FileHash -LiteralPath $progressPath -Algorithm SHA256).Hash
    $dq = Get-Content -LiteralPath (Join-Path $testRoot 'transfer-validation-dq.json') -Raw | ConvertFrom-Json
    $beatCount = & docker compose @prefix exec -T scheduler python -c 'from app.celery_app import celery_app;print(len(celery_app.conf.beat_schedule))'
    [pscustomobject]@{
        package_path=$package.FullName; test_path=$testRoot; compose_project=$install.composeProjectName
        setup_completed=$setupOk; windows_powershell_5_1_job_state=$setupState; idempotent_setup=$idempotent
        postgres_volume_unchanged=(($volumeBefore -join ',') -eq ($volumeAfter -join ','))
        setup_progress_unchanged=($progressHashBefore -eq $progressHashAfter)
        current_masters=$after.current_masters; source_opportunities=$after.source_opportunities
        observations=$after.observations; review_history=$after.review_history_records
        audit_events=$after.audit_events; merge_lineage=$after.merge_lineage_records
        source_configuration_sha256=$after.source_configuration_sha256; rbac_fingerprint_sha256=$after.rbac_fingerprint_sha256
        active_sync_jobs=$after.active_sync_jobs; sync_jobs_before=$before.sync_jobs; sync_jobs_after=$after.sync_jobs
        dq_counts=$dq.counts; dq_gates=$dq.gates_evaluated; beat_schedule_count=$beatCount
    } | ConvertTo-Json -Depth 5
    if (-not $idempotent) { throw 'Idempotent setup validation failed.' }
} catch {
    Write-Output ('VALIDATION_HARNESS_ERROR=' + $_.Exception.Message)
    exit 1
} finally {
    if ($pass) { $pass.Dispose() }
}
