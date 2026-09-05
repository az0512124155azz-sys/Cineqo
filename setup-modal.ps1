$ErrorActionPreference = 'Stop'

Write-Host 'Cineqo Modal setup' -ForegroundColor Cyan

if (-not (Get-Command modal -ErrorAction SilentlyContinue)) {
    Write-Host 'Installing Modal CLI...'
    python -m pip install -U modal
}

$profile = modal profile current
Write-Host "Active Modal profile: $profile"

$keyBytes = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Fill($keyBytes)
$key = [Convert]::ToHexString($keyBytes).ToLowerInvariant()

Write-Host 'Creating/updating Modal secret cineqo-api...'
modal secret create cineqo-api "CINEQO_MODAL_API_KEY=$key" --force

Write-Host 'Deploying Cineqo GPU backend...'
modal deploy deploy\modal\cineqo.py

Write-Host ''
Write-Host 'DEPLOY COMPLETE' -ForegroundColor Green
Write-Host 'Copy these two values into Render when prompted:' -ForegroundColor Yellow
Write-Host 'CINEQO_MODAL_URL = copy the https://...modal.run URL printed by modal deploy'
Write-Host "CINEQO_MODAL_API_KEY = $key"
Write-Host ''
Write-Host 'Do NOT send the API key to anyone and do NOT commit it to GitHub.' -ForegroundColor Yellow
