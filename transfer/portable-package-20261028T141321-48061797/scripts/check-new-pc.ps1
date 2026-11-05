$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
. (Join-Path $root 'scripts\portable-host-check.ps1')
$result = Test-PortableHost -HttpPort 8080
$validation = Join-Path $root 'docs\validation\deployment\portable-transfer'
New-Item -ItemType Directory -Path $validation -Force | Out-Null
$path = Join-Path $validation 'host-requirements.json'
[IO.File]::WriteAllText($path,($result | ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
foreach ($check in $result.checks) { Write-Host ("{0,-32} {1}  {2}" -f $check.key,$check.status,$check.observed) }
Write-Host "`nDetails: docs\validation\deployment\portable-transfer\host-requirements.json"
if (@($result.checks | Where-Object { $_.status -eq 'FAIL' }).Count) { exit 1 }
exit 0
