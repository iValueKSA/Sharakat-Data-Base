function ConvertTo-PortablePlainText([Security.SecureString]$SecureValue) {
    if (-not $SecureValue) { throw 'A private transfer passphrase is required.' }
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}

function Get-PortableKeyMaterial([string]$Passphrase, [byte[]]$Salt, [int]$Iterations) {
    $derive = [Security.Cryptography.Rfc2898DeriveBytes]::new(
        $Passphrase, $Salt, $Iterations, [Security.Cryptography.HashAlgorithmName]::SHA256
    )
    try { return $derive.GetBytes(64) }
    finally { $derive.Dispose() }
}

function Protect-PortableSecret([string]$Value, [string]$Passphrase, [string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Value)) { throw 'The required session-signing secret is missing from local settings.' }
    $salt = New-Object byte[] 16; $iv = New-Object byte[] 16
    $random = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $random.GetBytes($salt); $random.GetBytes($iv) } finally { $random.Dispose() }
    $material = Get-PortableKeyMaterial -Passphrase $Passphrase -Salt $salt -Iterations 250000
    $aes = [Security.Cryptography.Aes]::Create()
    try {
        $aes.KeySize = 256; $aes.BlockSize = 128; $aes.Mode = [Security.Cryptography.CipherMode]::CBC
        $aes.Padding = [Security.Cryptography.PaddingMode]::PKCS7; $aes.Key = $material[0..31]; $aes.IV = $iv
        $bytes = [Text.Encoding]::UTF8.GetBytes($Value)
        $encryptor = $aes.CreateEncryptor()
        try { $cipher = $encryptor.TransformFinalBlock($bytes, 0, $bytes.Length) } finally { $encryptor.Dispose() }
        $macInput = [Text.Encoding]::UTF8.GetBytes(('v1|' + [Convert]::ToBase64String($salt) + '|' + [Convert]::ToBase64String($iv) + '|' + [Convert]::ToBase64String($cipher)))
        $hmac = [Security.Cryptography.HMACSHA256]::new($material[32..63])
        try { $tag = $hmac.ComputeHash($macInput) } finally { $hmac.Dispose() }
        $record = [ordered]@{ format = 'AHDA-PORTABLE-SECRET-v1'; kdf = 'PBKDF2-SHA256'; iterations = 250000; cipher = 'AES-256-CBC+HMAC-SHA256'; salt = [Convert]::ToBase64String($salt); iv = [Convert]::ToBase64String($iv); ciphertext = [Convert]::ToBase64String($cipher); authentication_tag = [Convert]::ToBase64String($tag) }
        [IO.File]::WriteAllText($Path, ($record | ConvertTo-Json -Depth 4), [Text.UTF8Encoding]::new($false))
    } finally {
        $aes.Dispose()
        [Array]::Clear($material, 0, $material.Length)
    }
}

function Unprotect-PortableSecret([string]$Path, [string]$Passphrase) {
    $record = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    if ($record.format -ne 'AHDA-PORTABLE-SECRET-v1' -or $record.kdf -ne 'PBKDF2-SHA256' -or $record.cipher -ne 'AES-256-CBC+HMAC-SHA256' -or [int]$record.iterations -ne 250000) {
        throw 'The encrypted transfer key format is unsupported.'
    }
    $salt = [Convert]::FromBase64String([string]$record.salt); $iv = [Convert]::FromBase64String([string]$record.iv)
    $cipher = [Convert]::FromBase64String([string]$record.ciphertext); $tag = [Convert]::FromBase64String([string]$record.authentication_tag)
    $material = Get-PortableKeyMaterial -Passphrase $Passphrase -Salt $salt -Iterations ([int]$record.iterations)
    try {
        $macInput = [Text.Encoding]::UTF8.GetBytes(('v1|' + [string]$record.salt + '|' + [string]$record.iv + '|' + [string]$record.ciphertext))
        $hmac = [Security.Cryptography.HMACSHA256]::new($material[32..63])
        try { $expected = $hmac.ComputeHash($macInput) } finally { $hmac.Dispose() }
        if ($expected.Length -ne $tag.Length) { throw 'The transfer passphrase is incorrect or the encrypted key was damaged.' }
        $difference = 0
        for ($i = 0; $i -lt $tag.Length; $i++) { $difference = $difference -bor ($expected[$i] -bxor $tag[$i]) }
        if ($difference -ne 0) { throw 'The transfer passphrase is incorrect or the encrypted key was damaged.' }
        $aes = [Security.Cryptography.Aes]::Create()
        try {
            $aes.KeySize = 256; $aes.BlockSize = 128; $aes.Mode = [Security.Cryptography.CipherMode]::CBC
            $aes.Padding = [Security.Cryptography.PaddingMode]::PKCS7; $aes.Key = $material[0..31]; $aes.IV = $iv
            $decryptor = $aes.CreateDecryptor()
            try { $plain = $decryptor.TransformFinalBlock($cipher, 0, $cipher.Length) } finally { $decryptor.Dispose() }
            return [Text.Encoding]::UTF8.GetString($plain)
        } finally { $aes.Dispose() }
    } finally { [Array]::Clear($material, 0, $material.Length) }
}
