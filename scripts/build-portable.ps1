[CmdletBinding()]
param(
    [switch]$IncludeOllama,
    [string]$OllamaSource = ""
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$env:UV_CACHE_DIR = Join-Path $ProjectRoot ".uv-cache"

function Write-Step([int]$Number, [string]$Text) {
    Write-Host ""
    Write-Host "[$Number/4] $Text" -ForegroundColor Cyan
}

Write-Step 1 "Sync Windows Native and packaging dependencies"
uv sync --group native
if ($LASTEXITCODE -ne 0) { throw "uv sync --group native failed" }

Write-Step 2 "Warm up and verify PaddleOCR"
$NativeCache = Join-Path $ProjectRoot ".native-cache\paddlex-cache"
New-Item -ItemType Directory -Force -Path $NativeCache | Out-Null
$env:PADDLE_PDX_CACHE_HOME = $NativeCache
$env:USERPROFILE = Join-Path $ProjectRoot ".native-cache\paddle-home"
$env:PADDLE_HOME = Join-Path $env:USERPROFILE ".cache\paddle"
uv run --group native python scripts/warm-ocr.py
if ($LASTEXITCODE -ne 0) { throw "PaddleOCR initialization failed" }

Write-Step 3 "Build the PyInstaller onedir distribution"
uv run --group native pyinstaller --noconfirm --clean BreastCancerExtractor.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

$PortableRoot = Join-Path $ProjectRoot "dist\BreastCancerExtractor"
@("database\patients", "models\llm", "local_knowledge", "logs") |
    ForEach-Object { New-Item -ItemType Directory -Force -Path (Join-Path $PortableRoot $_) | Out-Null }
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

Write-Step 4 "Write Portable documentation and build metadata"
git rev-parse HEAD | Set-Content -LiteralPath (Join-Path $PortableRoot "BUILD_COMMIT.txt") -Encoding ASCII
Copy-Item -LiteralPath "docs\WINDOWS_PORTABLE.md" -Destination (Join-Path $PortableRoot "WINDOWS_PORTABLE.md") -Force
Write-Host ""
Write-Host "Windows Portable created at: $PortableRoot" -ForegroundColor Green
