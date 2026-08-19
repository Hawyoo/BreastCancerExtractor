function Initialize-ProjectUv {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    $LocalRoot = Join-Path $ProjectRoot ".uv-local"
    $UvBinDir = Join-Path $LocalRoot "bin"
    $UvExe = Join-Path $UvBinDir "uv.exe"

    # Keep uv-owned state inside this project and avoid touching the user's PATH or registry.
    $env:UV_CACHE_DIR = Join-Path $ProjectRoot ".uv-cache"
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $LocalRoot "python"
    $env:UV_PYTHON_BIN_DIR = Join-Path $LocalRoot "python-bin"
    $env:UV_PYTHON_INSTALL_REGISTRY = "0"
    $env:UV_NO_MODIFY_PATH = "1"

    New-Item -ItemType Directory -Force -Path $LocalRoot, $UvBinDir, $env:UV_CACHE_DIR | Out-Null

    if (-not (Test-Path -LiteralPath $UvExe)) {
        Write-Host "uv was not found in this project. Installing a project-local copy..." -ForegroundColor Cyan

        # UV_UNMANAGED_INSTALL installs directly to the requested directory and disables shell changes/self-update.
        $env:UV_UNMANAGED_INSTALL = $UvBinDir
        try {
            $installer = Invoke-RestMethod -Uri "https://astral.sh/uv/install.ps1"
            Invoke-Expression $installer
        }
        catch {
            throw "Failed to install project-local uv: $($_.Exception.Message)"
        }
    }

    if (-not (Test-Path -LiteralPath $UvExe)) {
        throw "uv installer completed, but uv.exe was not found at $UvExe"
    }

    & $UvExe --version
    if ($LASTEXITCODE -ne 0) {
        throw "Project-local uv exists but could not be executed."
    }

    return $UvExe
}
