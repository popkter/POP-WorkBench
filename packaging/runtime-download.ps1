function Get-VerifiedRuntime {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [Parameter(Mandatory = $true)][string]$Destination,
        [Parameter(Mandatory = $true)]
        [ValidatePattern('^[a-fA-F0-9]{64}$')][string]$Sha256
    )

    $ExpectedHash = $Sha256.ToLowerInvariant()
    if (Test-Path -LiteralPath $Destination -PathType Leaf) {
        $CachedHash = (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($CachedHash -eq $ExpectedHash) { return }
        Write-Warning "Cached runtime checksum mismatch; downloading again: $Destination"
    }

    New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force | Out-Null
    $Download = "$Destination.download-$([guid]::NewGuid().ToString('N'))"
    try {
        Write-Host "Downloading runtime: $Uri"
        Invoke-WebRequest -Uri $Uri -OutFile $Download -MaximumRetryCount 3 `
            -RetryIntervalSec 3 -ErrorAction Stop
        $ActualHash = (Get-FileHash -LiteralPath $Download -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($ActualHash -ne $ExpectedHash) {
            throw "Runtime package checksum mismatch: $Destination"
        }
        Move-Item -LiteralPath $Download -Destination $Destination -Force
    }
    finally {
        if (Test-Path -LiteralPath $Download -PathType Leaf) {
            Remove-Item -LiteralPath $Download -Force
        }
    }
}
