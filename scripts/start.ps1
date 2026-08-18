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

function Find-DockerDesktop {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\DockerDesktop\Docker Desktop.exe"),
        (Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe")
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

function Test-DockerEngine {
    param([string]$DockerCli)
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $DockerCli info 1> $null 2> $null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }
}

try {
    Initialize-DockerCliConfig
    $dockerCli = Find-DockerCli
    $dockerDesktop = Find-DockerDesktop
    if (-not $dockerCli -or -not $dockerDesktop) {
        throw "Installation is incomplete. Run install.bat first."
    }

    if (-not (Test-DockerEngine -DockerCli $dockerCli)) {
        Write-Host "Starting Docker Desktop..."
        Start-Process -FilePath $dockerDesktop
        $deadline = (Get-Date).AddSeconds(180)
        do {
            Start-Sleep -Seconds 5
            $ready = Test-DockerEngine -DockerCli $dockerCli
        } while (-not $ready -and (Get-Date) -lt $deadline)
        if (-not $ready) {
            throw "Docker Engine startup timed out. Open Docker Desktop and check its status."
        }
    }

    # Daily startup reuses the images created by install.bat. Do not rebuild dependencies here.
    & $dockerCli compose up -d
    if ($LASTEXITCODE -ne 0) {
        throw "Startup failed. If this is the first run, run install.bat; otherwise check docker compose logs --tail 200."
    }

    $port = "8765"
    if (Test-Path -LiteralPath ".env") {
        $line = Get-Content -LiteralPath ".env" -Encoding UTF8 |
            Where-Object { $_ -match '^\s*APP_PORT\s*=\s*(\d+)\s*$' } |
            Select-Object -First 1
        if ($line -and $line -match '^\s*APP_PORT\s*=\s*(\d+)\s*$') {
            $port = $Matches[1]
        }
    }
    $url = "http://127.0.0.1:$port"
    Start-Process $url
    Write-Host "Breast Cancer Extractor started: $url" -ForegroundColor Green
    exit 0
}
catch {
    Write-Host "Startup failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
