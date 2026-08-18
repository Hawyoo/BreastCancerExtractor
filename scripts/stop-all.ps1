[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

function Find-DockerCli {
    $command = Get-Command docker.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $candidates = @(
        (Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\DockerDesktop\resources\bin\docker.exe")
    )
    return $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}

function Initialize-DockerCliConfig {
    if ($env:DOCKER_CONFIG) { return }
    $defaultConfig = Join-Path $env:USERPROFILE ".docker\config.json"
    try {
        if (Test-Path -LiteralPath $defaultConfig) {
            $stream = [IO.File]::Open($defaultConfig, "Open", "Read", "ReadWrite")
            $stream.Dispose()
            return
        }
    }
    catch {
        Write-Warning "The default Docker CLI config is not readable. Using an isolated local CLI config."
    }
    $localConfig = Join-Path $ProjectRoot ".docker-cli"
    New-Item -ItemType Directory -Force -Path $localConfig | Out-Null
    $env:DOCKER_CONFIG = $localConfig
}

try {
    Write-Warning "This will stop Docker Desktop and ALL WSL distributions, including unrelated WSL work."
    $answer = Read-Host "Enter Y to continue"
    if ($answer -notmatch '^[Yy]$') {
        Write-Host "Full shutdown cancelled."
        exit 2
    }

    Initialize-DockerCliConfig
    $dockerCli = Find-DockerCli
    if ($dockerCli) {
        Write-Host "Stopping Breast Cancer Extractor containers..."
        $previousPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & $dockerCli compose stop
        $ErrorActionPreference = $previousPreference

        Write-Host "Stopping Docker Desktop..."
        $previousPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & $dockerCli desktop stop
        $ErrorActionPreference = $previousPreference
    }
    else {
        Write-Host "Docker CLI was not found; continuing with WSL shutdown."
    }

    $wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
    if ($wsl) {
        Write-Host "Shutting down WSL..."
        & wsl.exe --shutdown
        if ($LASTEXITCODE -ne 0) {
            throw "wsl --shutdown failed."
        }
    }

    Start-Sleep -Seconds 2
    Write-Host "Full shutdown completed. vmmem may take several seconds to disappear." -ForegroundColor Green
    exit 0
}
catch {
    Write-Host "Full shutdown failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
