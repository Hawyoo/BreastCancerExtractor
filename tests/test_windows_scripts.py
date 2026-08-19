from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_one_click_install_and_start_scripts_exist():
    expected = [
        ROOT / "install.bat",
        ROOT / "start.bat",
        ROOT / "stop.bat",
        ROOT / "stop-all.bat",
        ROOT / "scripts/install.ps1",
        ROOT / "scripts/start.ps1",
        ROOT / "scripts/stop-all.ps1",
    ]
    assert all(path.is_file() for path in expected)


def test_installer_preserves_existing_env_and_checks_health():
    installer = (ROOT / "scripts/install.ps1").read_text(encoding="utf-8")
    assert 'if (-not (Test-Path -LiteralPath ".env"))' in installer
    assert "docker compose down -v" not in installer
    assert "/api/health" in installer
    assert "compose up -d --build" in installer


def test_daily_start_reuses_existing_docker_images():
    starter = (ROOT / "scripts/start.ps1").read_text(encoding="utf-8")
    assert "compose up -d --build" not in starter
    assert "compose up -d" in starter


def test_windows_native_portable_build_is_onedir_and_reuses_core_app():
    root = Path(__file__).resolve().parents[1]
    specification = (root / "BreastCancerExtractor.spec").read_text(encoding="utf-8")
    launcher = (root / "app/native_launcher.py").read_text(encoding="utf-8")
    builder = (root / "scripts/build-portable.ps1").read_text(encoding="utf-8")

    assert "COLLECT(" in specification
    assert 'name="BreastCancerExtractor"' in specification
    assert 'uvicorn.run("app.main:app"' in launcher
    assert 'uvicorn.run("ocr.service:app"' in launcher
    assert "pyinstaller --noconfirm --clean BreastCancerExtractor.spec" in builder


def test_windows_portable_ollama_is_optional():
    builder = (ROOT / "scripts/build-portable.ps1").read_text(encoding="utf-8")
    default_bat = (ROOT / "build-portable.bat").read_text(encoding="utf-8")
    ollama_bat = (ROOT / "build-portable-with-ollama.bat").read_text(encoding="utf-8")

    assert "[switch]$IncludeOllama" in builder
    assert "if ($IncludeOllama)" in builder
    assert "runtime\\ollama" in builder
    assert "-IncludeOllama" not in default_bat
    assert "-IncludeOllama" in ollama_bat


def test_docker_runtime_mode_remains_explicit():
    root = Path(__file__).resolve().parents[1]
    compose = (root / "compose.yaml").read_text(encoding="utf-8")
    assert "RUNTIME_MODE: docker" in compose
    assert "http://ollama:11434" in compose
    assert "http://ocr:8001" in compose


def test_readme_makes_windows_ollama_optional():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Ollama / 本地 AI 是可选项" in readme
    assert "build-portable.bat" in readme
    assert "build-portable-with-ollama.bat" in readme


def test_stop_all_closes_automatically_without_pause():
    script = (ROOT / "stop-all.bat").read_text(encoding="utf-8")
    assert "timeout /t 5 /nobreak" in script
    assert "pause" not in script.lower()


def test_installer_closes_automatically_without_pause():
    script = (ROOT / "install.bat").read_text(encoding="utf-8")
    assert script.count("timeout /t 5 /nobreak") == 2
    assert "pause" not in script.lower()
