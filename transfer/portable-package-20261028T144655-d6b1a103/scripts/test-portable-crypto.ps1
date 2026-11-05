$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'portable-crypto.ps1')
$path = Join-Path $env:TEMP ('ahda-portable-crypto-' + [guid]::NewGuid().ToString('N') + '.json')
$sample = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
$passphrase = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
try {
    Protect-PortableSecret -Value $sample -Passphrase $passphrase -Path $path
    $ciphertext = Get-Content -LiteralPath $path -Raw
    if ($ciphertext.Contains($sample)) { throw 'Portable encryption unexpectedly contains cleartext.' }
    if ((Unprotect-PortableSecret -Path $path -Passphrase $passphrase) -cne $sample) { throw 'Portable encryption round-trip mismatched.' }
    $wrongPassphraseRejected = $false
    try { $null = Unprotect-PortableSecret -Path $path -Passphrase ([guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')) } catch { $wrongPassphraseRejected = $true }
    if (-not $wrongPassphraseRejected) { throw 'A wrong transfer passphrase was not rejected.' }
    Write-Host 'PORTABLE_CRYPTO_ROUNDTRIP=PASSED'
    Write-Host 'PORTABLE_CRYPTO_AUTHENTICATION=PASSED'
    Write-Host 'PORTABLE_CRYPTO_CLEAR_TEXT_CHECK=PASSED'
} finally {
    Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
}
