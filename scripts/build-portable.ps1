[CmdletBinding()]
param(
    [switch]$IncludeOllama,
    [string]$OllamaSource = ""
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

. (Join-Path $PSScriptRoot "uv-bootstrap.ps1")
$UvExe = Initialize-ProjectUv -ProjectRoot $ProjectRoot

function Write-Step([int]$Number, [string]$Text) {
    Write-Host ""
    Write-Host "[$Number/5] $Text" -ForegroundColor Cyan
}

Write-Step 1 "Sync Windows Native and packaging dependencies"
& $UvExe sync --group native
if ($LASTEXITCODE -ne 0) { throw "uv sync --group native failed" }

Write-Step 2 "Warm up and verify PaddleOCR inference"
$NativeCache = Join-Path $ProjectRoot ".native-cache\paddlex-cache"
New-Item -ItemType Directory -Force -Path $NativeCache | Out-Null
$env:PADDLE_PDX_CACHE_HOME = $NativeCache
$env:USERPROFILE = Join-Path $ProjectRoot ".native-cache\paddle-home"
$env:PADDLE_HOME = Join-Path $env:USERPROFILE ".cache\paddle"
& $UvExe run --group native python scripts/warm-ocr.py
if ($LASTEXITCODE -ne 0) {
    throw "PaddleOCR inference warm-up failed. If a cached model is incomplete, delete .native-cache\paddlex-cache\official_models and rebuild while online."
}

Write-Step 3 "Prepare the Windows icon and build the PyInstaller onedir distribution"
$SourceIcon = Join-Path $ProjectRoot "BreastCancerExtractor.ico"
$BuildIcon = Join-Path $ProjectRoot ".build-assets\BreastCancerExtractor.ico"
& $UvExe run --group native python scripts/prepare-windows-icon.py $SourceIcon $BuildIcon
if ($LASTEXITCODE -ne 0) {
    throw "Windows executable icon preparation failed. The build requires a valid BreastCancerExtractor.ico source image."
}
$env:BCE_BUILD_ICON = $BuildIcon
try {
    & $UvExe run --group native pyinstaller --noconfirm --clean BreastCancerExtractor.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }
}
finally {
    Remove-Item Env:BCE_BUILD_ICON -ErrorAction SilentlyContinue
}

$PortableRoot = Join-Path $ProjectRoot "dist\BreastCancerExtractor"
@("database\patients", "config", "runtime", "models\llm", "local_knowledge", "logs") |
    ForEach-Object { New-Item -ItemType Directory -Force -Path (Join-Path $PortableRoot $_) | Out-Null }

$PortableCache = Join-Path $PortableRoot "runtime\paddlex-cache"
if (Test-Path -LiteralPath $PortableCache) {
    Remove-Item -LiteralPath $PortableCache -Recurse -Force
}
if (Test-Path -LiteralPath $NativeCache) {
    Copy-Item -LiteralPath $NativeCache -Destination (Join-Path $PortableRoot "runtime") -Recurse -Force
}

if ($IncludeOllama) {
    if (-not $OllamaSource) {
        $OllamaCommand = Get-Command ollama.exe -ErrorAction SilentlyContinue
        if ($OllamaCommand) { $OllamaSource = Split-Path -Parent $OllamaCommand.Source }
    }
    $OllamaExe = if ($OllamaSource) { Join-Path $OllamaSource "ollama.exe" } else { "" }
    if (-not $OllamaExe -or -not (Test-Path -LiteralPath $OllamaExe)) {
        throw "-IncludeOllama was requested, but ollama.exe was not found. Install Ollama first or pass -OllamaSource."
    }

    $PortableOllama = Join-Path $PortableRoot "runtime\ollama"
    New-Item -ItemType Directory -Force -Path $PortableOllama | Out-Null
    Copy-Item -LiteralPath $OllamaExe -Destination (Join-Path $PortableOllama "ollama.exe") -Force
    if (Test-Path -LiteralPath (Join-Path $OllamaSource "lib")) {
        Copy-Item -LiteralPath (Join-Path $OllamaSource "lib") -Destination $PortableOllama -Recurse -Force
    }
    Write-Host "Bundled optional Ollama runtime from: $OllamaSource" -ForegroundColor Green
}
else {
    Write-Host "Ollama not bundled (default). Portable will run OCR-only unless a system Ollama is available." -ForegroundColor DarkGray
}

Write-Step 4 "Verify OCR inference from the finished Portable"
$PortableExe = Join-Path $PortableRoot "BreastCancerExtractor.exe"
$SelfTest = Start-Process -FilePath $PortableExe -ArgumentList "--ocr-self-test" -Wait -PassThru
if ($SelfTest.ExitCode -ne 0) {
    throw "Finished Portable failed the OCR inference self-test. See logs\ocr-self-test.log in the Portable directory. The dist package was not validated and must not be distributed."
}

Write-Step 5 "Write Portable documentation and build metadata"
git rev-parse HEAD | Set-Content -LiteralPath (Join-Path $PortableRoot "BUILD_COMMIT.txt") -Encoding ASCII
Copy-Item -LiteralPath "docs\WINDOWS_PORTABLE.md" -Destination (Join-Path $PortableRoot "WINDOWS_PORTABLE.md") -Force
Write-Host ""
Write-Host "Windows Portable created at: $PortableRoot" -ForegroundColor Green
