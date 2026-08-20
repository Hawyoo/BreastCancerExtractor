[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

try {
    . (Join-Path $PSScriptRoot "uv-bootstrap.ps1")
    $UvExe = Initialize-ProjectUv -ProjectRoot $ProjectRoot

    Write-Host "Starting Breast Cancer Extractor (Windows Native)..." -ForegroundColor Cyan
    & $UvExe run --group native python -m app.native_entry
    if ($LASTEXITCODE -ne 0) {
        throw "Windows Native startup failed with exit code $LASTEXITCODE."
    }
    exit 0
}
catch {
    Write-Host "Startup failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
