$ErrorActionPreference = 'Stop'

Write-Host 'Cineqo Modal setup' -ForegroundColor Cyan

if (-not (Get-Command modal -ErrorAction SilentlyContinue)) {
    Write-Host 'Installing Modal CLI...'
    python -m pip install -U modal
}

$profile = modal profile current
Write-Host "Active Modal profile: $profile"

# Generate a 32-byte random API key in a way that works on Windows PowerShell 5.1
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try {
    $keyBytes = New-Object byte[] 32
    $rng.GetBytes($keyBytes)
}
finally {
    $rng.Dispose()
}
$key = -join ($keyBytes | ForEach-Object { $_.ToString('x2') })
$keyFile = Join-Path $PSScriptRoot '.cineqo-modal-key.txt'
Set-Content -Path $keyFile -Value $key -NoNewline

Write-Host 'Creating/updating Modal secret cineqo-api...'
modal secret create cineqo-api "CINEQO_MODAL_API_KEY=$key" --force
if ($LASTEXITCODE -ne 0) { throw "Modal secret creation failed with exit code $LASTEXITCODE" }

Write-Host 'Deploying Cineqo GPU backend...'
modal deploy deploy\modal\cineqo.py
if ($LASTEXITCODE -ne 0) {
    Write-Host ''
    Write-Host 'DEPLOY FAILED' -ForegroundColor Red
    Write-Host "A fresh API key was written locally to $keyFile and stored in Modal, but no successful deployment was confirmed."
    throw "Modal deploy failed with exit code $LASTEXITCODE"
}

Write-Host ''
Write-Host 'DEPLOY COMPLETE' -ForegroundColor Green
Write-Host 'For Render you will need:' -ForegroundColor Yellow
Write-Host 'CINEQO_MODAL_URL = copy the https://...modal.run URL printed by modal deploy'
Write-Host "CINEQO_MODAL_API_KEY = read it locally from $keyFile"
Write-Host ''
Write-Host 'Do NOT paste the API key into chat or commit the local key file.' -ForegroundColor Yellow
