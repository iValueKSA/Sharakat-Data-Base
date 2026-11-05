param([switch]$OpenBrowser)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
. (Join-Path $root 'scripts\local-platform.ps1')
$logDir = Join-Path $root 'logs'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$outputPath = Join-Path $logDir ('verification-' + $stamp + '.json')

function Invoke-CheckCompose([string[]]$Arguments,[switch]$AllowFailure) {
    $dockerArgs = (Get-ComposePrefix) + $Arguments
    $previousErrorAction = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = & $script:DockerPath @dockerArgs 2>&1
        $script:LastExitCode = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previousErrorAction }
    if ($script:LastExitCode -ne 0 -and -not $AllowFailure) { throw 'A non-destructive Compose health check failed.' }
    return ($output -join [Environment]::NewLine)
}

function Get-CheckSnapshot {
    $raw = Invoke-CheckCompose -Arguments @('run','--rm','--no-deps','-T','migrate','python','scripts/portable_transfer_snapshot.py')
    $jsonLine = @($raw -split "`r?`n" | Where-Object { $_.Trim().StartsWith('{') } | Select-Object -Last 1)
    if (-not $jsonLine) { throw 'The read-only database count snapshot returned no JSON.' }
    return ($jsonLine[0] | ConvertFrom-Json)
}

function Get-ReadOnlyDq {
    $raw = Invoke-CheckCompose -Arguments @('run','--rm','--no-deps','-T','migrate','python','-m','scripts.run_data_quality','--scope','full') -AllowFailure
    $start = $raw.IndexOf('{')
    if ($start -lt 0) { return [pscustomobject]@{ valid=$false; exit_code=$script:LastExitCode; fail=$null; warning=$null; pass=$null } }
    $result = $raw.Substring($start) | ConvertFrom-Json
    return [pscustomobject]@{ valid=$true; exit_code=$script:LastExitCode; fail=[int]$result.counts.fail; warning=[int]$result.counts.warning; pass=[int]$result.counts.pass; gates=[int]$result.gates_evaluated }
}

function Add-Check([string]$Key,[bool]$Passed,[object]$Observed) {
    $script:Checks.Add([ordered]@{ key=$Key; status=if ($Passed) {'PASS'} else {'FAIL'}; observed=$Observed })
}

try {
    if (-not (Test-Path -LiteralPath '.env.local')) { throw 'The private local environment file is missing; verification did not generate or replace it.' }
    $script:DockerPath = Find-DockerCli
    if (-not $script:DockerPath) { throw 'Docker CLI is not installed.' }
    & $script:DockerPath info *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Docker Engine is not running.' }
    $checks = [System.Collections.Generic.List[object]]::new(); $script:Checks = $checks
    Add-Check 'docker_engine' $true 'running'
    $compose = & $script:DockerPath compose version 2>&1
    Add-Check 'docker_compose' ($LASTEXITCODE -eq 0) (($compose | Out-String).Trim())
    if ($LASTEXITCODE -ne 0) { throw 'Docker Compose v2 is not available.' }
    $null = Invoke-CheckCompose -Arguments @('config','--quiet')
    Add-Check 'compose_configuration' $true 'valid'

    $servicesRaw = Invoke-CheckCompose -Arguments @('ps','--all','--format','json') -AllowFailure
    $services = @()
    foreach ($line in ($servicesRaw -split "`r?`n" | Where-Object { $_.Trim() })) { try { $services += ($line | ConvertFrom-Json) } catch { } }
    foreach ($serviceName in @('db','redis','api','frontend','worker','scheduler')) {
        $item = $services | Where-Object { $_.Service -eq $serviceName } | Select-Object -First 1
        $running = [bool]($item -and $item.State -match 'running|up')
        $healthy = if ($item -and $item.Health) { $item.Health -eq 'healthy' } else { $running }
        $observedState = if ($item) { "$($item.State)/$($item.Health)" } else { 'not present' }
        Add-Check ("service_" + $serviceName) ($running -and $healthy) $observedState
    }
    $live = Invoke-RestMethod -Uri ($script:LocalBaseUrl.TrimEnd('/') + '/health/live') -TimeoutSec 5
    $ready = Invoke-RestMethod -Uri ($script:LocalBaseUrl.TrimEnd('/') + '/health/ready') -TimeoutSec 5
    $front = Invoke-WebRequest -Uri ($script:LocalBaseUrl.TrimEnd('/') + '/') -UseBasicParsing -TimeoutSec 5
    Add-Check 'health_live' ($live -ne $null) 'HTTP 200'
    Add-Check 'health_ready' ($ready.status -eq 'ready') ([string]$ready.status)
    Add-Check 'frontend' ($front.StatusCode -eq 200) ([int]$front.StatusCode)

    $heads = Invoke-CheckCompose -Arguments @('run','--rm','--no-deps','migrate','alembic','heads')
    $current = Invoke-CheckCompose -Arguments @('run','--rm','--no-deps','migrate','alembic','current')
    $headValues = @([regex]::Matches($heads,'(?m)^([A-Za-z0-9_]+)\s+\(head\)\s*$') | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique)
    $currentValues = @([regex]::Matches($current,'(?m)^([A-Za-z0-9_]+)(?:\s+\(head\))?\s*$') | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique)
    $atHead = $headValues.Count -gt 0 -and ($headValues -join '|') -eq ($currentValues -join '|')
    Add-Check 'alembic_at_head' $atHead @{ heads=$headValues; current=$currentValues }

    $workerPing = Invoke-CheckCompose -Arguments @('exec','-T','worker','celery','-A','app.celery_app:celery_app','inspect','ping') -AllowFailure
    Add-Check 'celery_worker_ping' ($script:LastExitCode -eq 0 -and $workerPing -match 'pong') 'worker responded'
    $beatLogs = Invoke-CheckCompose -Arguments @('logs','--no-color','--tail','80','scheduler') -AllowFailure
    Add-Check 'celery_beat_started' ($script:LastExitCode -eq 0 -and $beatLogs -match 'celery beat|beat: Starting') 'scheduler startup log observed'

    $snapshot = Get-CheckSnapshot
    Add-Check 'database_snapshot' $true 'read-only count/fingerprint query succeeded'
    Add-Check 'active_admin_account' ([int]$snapshot.active_admin_users -gt 0) ([int]$snapshot.active_admin_users)
    Add-Check 'masters_and_merge_lineage' ([int]$snapshot.total_masters -eq ([int]$snapshot.current_masters + [int]$snapshot.merged_masters) -and [int]$snapshot.merge_lineage_records -ge [int]$snapshot.merged_masters) ([ordered]@{ total=$snapshot.total_masters; current=$snapshot.current_masters; merged=$snapshot.merged_masters; merge_audit=$snapshot.merge_lineage_records })
    Add-Check 'review_backlog_observed' $true ([ordered]@{ total=$snapshot.review_history_records; open=$snapshot.open_review_records })

    $baselinePath = Join-Path $root 'expected-data-manifest.json'
    $baselineMatches = $null
    if ($script:IsPortableInstallation -and (Test-Path -LiteralPath $baselinePath)) {
        $baseline = (Get-Content -LiteralPath $baselinePath -Raw | ConvertFrom-Json).snapshot
        $stable = @('total_masters','current_masters','merged_masters','source_opportunities','qualification_reviews','location_reviews','duplicate_reviews','conflict_reviews','review_history_records','open_review_records','merge_lineage_records','configured_sources','enabled_sources','source_configuration_sha256','users','active_admin_users','rbac_fingerprint_sha256','alembic_heads')
        $diffs = @($stable | Where-Object { (($snapshot.($_) | ConvertTo-Json -Depth 6 -Compress) -cne ($baseline.($_) | ConvertTo-Json -Depth 6 -Compress)) })
        $baselineMatches = ($diffs.Count -eq 0)
        Add-Check 'transfer_business_baseline' $baselineMatches ([ordered]@{ differences=$diffs; observations=$snapshot.observations; baseline_observations=$baseline.observations; jobs=$snapshot.sync_jobs; baseline_jobs=$baseline.sync_jobs })
    }
    $dq = Get-ReadOnlyDq
    Add-Check 'read_only_data_quality' ($dq.valid -and $dq.fail -eq 0) $dq
    foreach ($privateService in @('db','redis')) {
        $privateContainer = $services | Where-Object { $_.Service -eq $privateService } | Select-Object -First 1
        $publicBindings = @($privateContainer.Publishers | Where-Object { [int]$_.PublishedPort -gt 0 -and -not [string]::IsNullOrWhiteSpace([string]$_.URL) })
        $isPublic = $publicBindings.Count -gt 0
        Add-Check ($privateService + '_publicly_exposed') (-not $isPublic) $publicBindings
    }

    $result = [ordered]@{ checked_at_utc=(Get-Date).ToUniversalTime().ToString('o'); instance_mode=if ($script:IsPortableInstallation) {'portable'} else {'existing-local'}; base_url=$script:LocalBaseUrl; read_only=$true; manual_source_sync_started=$false; snapshot=$snapshot; checks=@($checks.ToArray()); summary=[ordered]@{ total=$checks.Count; pass=@($checks | Where-Object status -eq 'PASS').Count; fail=@($checks | Where-Object status -eq 'FAIL').Count }; baseline_matches=$baselineMatches }
    [IO.File]::WriteAllText($outputPath,($result | ConvertTo-Json -Depth 10),[Text.UTF8Encoding]::new($false))
    foreach ($check in $checks) { Write-Host ("{0,-34} {1}" -f $check.key,$check.status) }
    Write-Host "`nVerification report: logs\$(Split-Path -Leaf $outputPath)"
    if ($OpenBrowser) { Start-Process $script:LocalBaseUrl }
    if ($result.summary.fail -gt 0) { exit 1 }
    exit 0
} catch {
    Write-Host "VERIFICATION FAILED at line $($_.InvocationInfo.ScriptLineNumber): $($_.Exception.Message)" -ForegroundColor Red
    if ($_.ScriptStackTrace) { Write-Host $_.ScriptStackTrace }
    Write-Host 'No source sync or business-data updates were triggered.'
    exit 1
}
