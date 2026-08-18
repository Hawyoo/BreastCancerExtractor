[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

function Write-Step {
    param([int]$Number, [string]$Message)
    Write-Host ""
    Write-Host "[$Number/7] $Message" -ForegroundColor Cyan
}

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Find-DockerCli {
    $command = Get-Command docker.exe -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

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
    if ($env:DOCKER_CONFIG) {
        return
    }
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
    if (-not $DockerCli) {
        return $false
    }
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

function Wait-DockerEngine {
    param([string]$DockerCli, [int]$TimeoutSeconds = 180)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if (Test-DockerEngine -DockerCli $DockerCli) {
            return $true
        }
        Write-Host "Waiting for Docker Engine..." -ForegroundColor DarkGray
        Start-Sleep -Seconds 5
    } while ((Get-Date) -lt $deadline)
    return $false
}

function Get-AppPort {
    $port = "8765"
    if (Test-Path -LiteralPath ".env") {
        $match = Get-Content -LiteralPath ".env" -Encoding UTF8 |
            Where-Object { $_ -match '^\s*APP_PORT\s*=\s*(\d+)\s*$' } |
            Select-Object -First 1
        if ($match -and $match -match '^\s*APP_PORT\s*=\s*(\d+)\s*$') {
            $port = $Matches[1]
        }
    }
    return $port
}

try {
    Write-Step 1 "Checking Windows, CPU virtualization, and disk space"
    if (-not [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform(
        [System.Runtime.InteropServices.OSPlatform]::Windows
    )) {
        throw "This installer only supports Windows."
    }

    $architecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
    Write-Host "Windows architecture: $architecture"
    try {
        $virtualization = Get-CimInstance Win32_Processor |
            Select-Object -ExpandProperty VirtualizationFirmwareEnabled -First 1
        if ($virtualization -eq $false) {
            throw "CPU virtualization is disabled in BIOS/UEFI. Enable Intel VT-x or AMD-V and run install.bat again."
        }
        Write-Host "CPU virtualization: enabled" -ForegroundColor Green
    }
    catch {
        if ($_.Exception.Message -like "CPU virtualization*") {
            throw
        }
        Write-Warning "Could not read virtualization status. Check Task Manager if WSL or Docker fails."
    }

    $projectDrive = Get-PSDrive -Name ([IO.Path]::GetPathRoot($ProjectRoot).TrimEnd(':', '\'))
    $freeGb = [math]::Round($projectDrive.Free / 1GB, 1)
    if ($freeGb -gt 0) {
        Write-Host "Free space on the project drive: $freeGb GB"
    }
    else {
        Write-Warning "Could not read free disk space in the current environment."
    }
    if ($freeGb -gt 0 -and $freeGb -lt 20) {
        Write-Warning "Less than 20 GB is free. Docker images and LLM models may not fit."
    }

    Write-Step 2 "Checking WSL2"
    $wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
    $wslReady = $false
    if ($wsl) {
        $previousPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            & wsl.exe --status 1> $null 2> $null
            $wslReady = $LASTEXITCODE -eq 0
        }
        catch {
            $wslReady = $false
        }
        finally {
            $ErrorActionPreference = $previousPreference
        }
    }
    if (-not $wslReady) {
        if (-not (Test-Administrator)) {
            Write-Host "Administrator permission is required to install WSL." -ForegroundColor Yellow
            $arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
            $elevated = Start-Process powershell.exe -Verb RunAs -ArgumentList $arguments -Wait -PassThru
            exit $elevated.ExitCode
        }

        Write-Host "Installing WSL. Windows may require a restart." -ForegroundColor Yellow
        & wsl.exe --install
        if ($LASTEXITCODE -ne 0) {
            throw "WSL installation failed. Check Windows Update and the network, then retry."
        }
        Write-Host "WSL installation was submitted. Restart Windows, then run install.bat again." -ForegroundColor Yellow
        exit 10
    }
    Write-Host "WSL2: installed" -ForegroundColor Green

    Write-Step 3 "Checking Docker Desktop"
    Initialize-DockerCliConfig
    $dockerCli = Find-DockerCli
    $dockerDesktop = Find-DockerDesktop
    if (-not $dockerCli -or -not $dockerDesktop) {
        Write-Warning "Docker Desktop is not installed. Institutions must review Docker Desktop licensing before use."
        $answer = Read-Host "Install Docker Desktop with Windows Package Manager now? Enter Y to continue"
        if ($answer -notmatch '^[Yy]$') {
            Start-Process "https://docs.docker.com/desktop/setup/install/windows-install/"
            throw "Automatic installation was cancelled. Install Docker Desktop and run install.bat again."
        }

        $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
        if (-not $winget) {
            Start-Process "https://docs.docker.com/desktop/setup/install/windows-install/"
            throw "winget is unavailable. The official Docker install page was opened. Install it and retry."
        }

        & winget.exe install --exact --id Docker.DockerDesktop --source winget `
            --accept-source-agreements --accept-package-agreements
        if ($LASTEXITCODE -ne 0) {
            throw "Docker Desktop installation failed. Install it from the official page and retry."
        }
        $dockerCli = Find-DockerCli
        $dockerDesktop = Find-DockerDesktop
        if (-not $dockerCli -or -not $dockerDesktop) {
            throw "Docker Desktop was installed but is not yet visible to this terminal. Restart Windows and retry."
        }
    }
    Write-Host "Docker Desktop: installed" -ForegroundColor Green

    Write-Step 4 "Starting Docker Engine"
    if (-not (Test-DockerEngine -DockerCli $dockerCli)) {
        Start-Process -FilePath $dockerDesktop
        if (-not (Wait-DockerEngine -DockerCli $dockerCli)) {
            throw "Docker Engine startup timed out. Open Docker Desktop, resolve its error, and retry."
        }
    }
    & $dockerCli compose version
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose is unavailable. Update Docker Desktop."
    }
    Write-Host "Docker Engine: ready" -ForegroundColor Green

    Write-Step 5 "Creating local configuration and persistent directories"
    if (-not (Test-Path -LiteralPath ".env")) {
        Copy-Item -LiteralPath ".env.example" -Destination ".env"
        Write-Host "Created .env from .env.example."
    }
    else {
        Write-Host ".env already exists and was preserved."
    }
    @("database\patients", "models\llm", "local_knowledge") | ForEach-Object {
        New-Item -ItemType Directory -Force -Path $_ | Out-Null
    }

    Write-Step 6 "Building and starting Breast Cancer Extractor"
    & $dockerCli compose up -d --build
    if ($LASTEXITCODE -ne 0) {
        throw "Container build or startup failed. Run docker compose logs --tail 200 for details."
    }

    Write-Step 7 "Checking services and opening the browser"
    $port = Get-AppPort
    $healthUrl = "http://127.0.0.1:$port/api/health"
    $appUrl = "http://127.0.0.1:$port"
    $healthy = $false
    1..30 | ForEach-Object {
        if (-not $healthy) {
            try {
                $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 3
                $healthy = $health.status -eq "ok" -and $health.ocr.available -and $health.ollama.available
            }
            catch {
                Start-Sleep -Seconds 2
            }
        }
    }
    if (-not $healthy) {
        & $dockerCli compose logs --tail 100 app
        & $dockerCli compose logs --tail 100 ocr
        & $dockerCli compose logs --tail 100 ollama
        throw "App, OCR, or Ollama health check failed."
    }

    & $dockerCli compose ps
    Start-Process $appUrl
    Write-Host ""
    Write-Host "Installation succeeded: $appUrl" -ForegroundColor Green
    Write-Host "The app can start without an LLM. A GGUF model can be imported later from models\llm."
    exit 0
}
catch {
    Write-Host ""
    Write-Host "Installation did not complete: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
