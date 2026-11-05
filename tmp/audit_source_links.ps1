$rows = Get-Content -LiteralPath 'tmp/source-link-input-current.json' -Raw -Encoding utf8 | ConvertFrom-Json
$results = $rows | ForEach-Object -Parallel {
    $row = $_
    $url = $row.url
    if ($row.source_key -eq 'furas') {
        $type = [string]$row.raw.attributes.OPPORTUNITYTYPE
        if ($type -eq 'TemporaryRental') { $type = 'TempRental' }
        $ref = [string]$row.reference
        if ($ref -match '^[A-Za-z0-9][A-Za-z0-9._/-]{2,199}$' -and $type) {
            $url = "https://furas.momah.gov.sa/index.php/ar/opportunity/$ref`?type=$([uri]::EscapeDataString($type))"
        } else { $url = '' }
    }
    $class = 'MISSING_URL'; $status = $null; $final = $null; $redirects = 0
    $titleMatch = $false; $referenceMatch = $false; $pathIdentity = $false; $fragmentTargetMatch = $false
    $ownerMatch = $false; $locationMatch = $false; $requestError = $null
    if ($url) {
        try {
            $response = Invoke-WebRequest -Uri $url -Method Get -MaximumRedirection 8 -TimeoutSec 22 -SkipHttpErrorCheck -Headers @{
                'User-Agent' = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36'
                'Accept-Language' = 'ar,en-US;q=0.9,en;q=0.8'
                'Accept' = 'text/html,application/xhtml+xml,application/pdf,*/*;q=0.8'
            }
            $status = [int]$response.StatusCode
            $final = $response.BaseResponse.RequestMessage.RequestUri.AbsoluteUri
            $redirects = if ($final -ne $url) { 1 } else { 0 }
            $body = [string]$response.Content
            $text = [System.Net.WebUtility]::HtmlDecode([regex]::Replace($body, '<[^>]+>', ' '))
            $normalizer = { param($v) ([regex]::Replace(([string]$v).ToLowerInvariant(), '[^\p{L}\p{N}]', '')) }
            $titleNeedle = & $normalizer $row.title
            $bodyText = & $normalizer $text
            $titleMatch = [bool]($titleNeedle.Length -gt 0 -and $bodyText.Contains($titleNeedle))
            $ref = [string]$row.reference
            $external = [string]$row.external_id
            $referenceMatch = [bool](($ref.Length -gt 0 -and $text.Contains($ref)) -or ($external.Length -gt 0 -and $text.Contains($external)))
            $bodyUri = [uri]$final; $requestedUri = [uri]$url
            $sameHost = $bodyUri.Host.Replace('www.','') -eq $requestedUri.Host.Replace('www.','')
            $finalPath = [uri]::UnescapeDataString($bodyUri.AbsolutePath).TrimEnd('/')
            $expectedPath = [uri]::UnescapeDataString($requestedUri.AbsolutePath).TrimEnd('/')
            if ($row.source_key -eq 'kfu' -and $requestedUri.Fragment) {
                $fragment = [uri]::UnescapeDataString($requestedUri.Fragment.TrimStart('#'))
                $escapedFragment = [regex]::Escape($fragment)
                $fragmentPattern = '(?is)\bid\s*=\s*["'']' + $escapedFragment + '["'']'
                $fragmentTargetMatch = [bool]($body -match $fragmentPattern)
            }
            switch ($row.source_key) {
                'furas' { $pathIdentity = $sameHost -and $finalPath.EndsWith('/opportunity/' + $ref) }
                'alahsa-opportunities' { $pathIdentity = $sameHost -and $finalPath.EndsWith('/opportunities/' + [string]$row.external_id) }
                default { $pathIdentity = $sameHost -and $finalPath -eq $expectedPath }
            }
            if ($row.source_key -eq 'furas') {
                $rawAttributes = $row.raw.attributes
                $owner = [string]$rawAttributes.AMANA
                $location = [string]($rawAttributes.DISTRICT ?? $rawAttributes.CITYNAME)
            } else {
                $owner = [string]$row.owner
                $location = [string]$row.location
            }
            if ($owner) { $ownerMatch = $text.Contains($owner) }
            if ($location) { $locationMatch = $text.Contains($location) }
            $errorPage = $bodyText.Contains((& $normalizer 'الصفحة غير موجودة')) -or $bodyText.Contains('pagenotfound') -or $bodyText.Contains('recordnotfound')
            if ($status -eq 404) { $class = 'HTTP_404' }
            elseif ($status -eq 410) { $class = 'HTTP_410' }
            elseif ($status -eq 403) { $class = 'HTTP_403' }
            elseif ($status -eq 401 -or $final -match '(?i)login|signin') { $class = 'LOGIN_REQUIRED' }
            elseif ($status -ge 500) { $class = 'SOURCE_ERROR' }
            elseif ($status -eq 200 -and -not $errorPage -and $titleMatch -and $pathIdentity -and ($referenceMatch -or $locationMatch -or $row.source_key -in @('ahda','invest-saudi','ncp') -or ($row.source_key -eq 'kfu' -and $fragmentTargetMatch))) {
                $class = if ($redirects -gt 0) { 'VALID_REDIRECT' } else { 'VALID_200' }
            }
            elseif ($status -eq 200) { $class = 'HTTP_200_BUT_CONTENT_MISMATCH' }
            else { $class = 'SOURCE_ERROR' }
        } catch {
            $requestError = $_.Exception.Message
            if ($requestError -match '(?i)timed out|timeout') { $class = 'NETWORK_ERROR' } else { $class = 'NETWORK_ERROR' }
        }
    }
    [pscustomobject]@{
        source_record_id = [int]$row.source_record_id; master_id = [int]$row.master_id
        source_key = [string]$row.source_key; source_name = [string]$row.source_name
        external_id = [string]$row.external_id; reference = [string]$row.reference
        title = [string]$row.title; owner = [string]$row.owner; location = [string]$row.location
        stored_url = [string]$row.url; current_url = [string]$url; class = $class
        http_status = $status; final_url = $final; redirect_count = $redirects
        title_match = $titleMatch; reference_match = $referenceMatch
        url_path_identity_match = $pathIdentity; fragment_target_match = $fragmentTargetMatch; owner_match = $ownerMatch; location_match = $locationMatch
        source_lifecycle_status = [string]$row.source_status
        missing_successful_checks = [int]$row.missing_checks
        master_status = [string]$row.master_status; error = $requestError
    }
} -ThrottleLimit 8
$results | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath 'tmp/source-link-final-audit-current.json' -Encoding utf8
$results | Group-Object source_key,class | Sort-Object Name | ForEach-Object { '{0}: {1}' -f $_.Name,$_.Count }
