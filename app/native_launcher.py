from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

APP_HOST = "127.0.0.1"
DEFAULT_APP_PORT = 8765
OCR_PORT = 8001
OLLAMA_PORT = int(os.getenv("BCE_OLLAMA_PORT", "11434"))


def _portable_root() -> Path:
    configured = os.getenv("BCE_PORTABLE_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def configure_native_environment(root: Path | None = None) -> Path:
    root = (root or _portable_root()).resolve()
    os.environ["BCE_PORTABLE_ROOT"] = str(root)
    os.environ["RUNTIME_MODE"] = "windows_native"
    os.environ["DATABASE_PATH"] = str(root / "database" / "extractor.db")
    os.environ["WORKSPACE_PATH"] = str(root / "workspace")
    os.environ["MODEL_IMPORT_PATH"] = str(root / "models" / "llm")
    os.environ["OLLAMA_URL"] = f"http://{APP_HOST}:{OLLAMA_PORT}"
    os.environ["OCR_URL"] = f"http://{APP_HOST}:{OCR_PORT}"
    os.environ["PADDLE_PDX_CACHE_HOME"] = str(root / "runtime" / "paddlex-cache")
    os.environ.setdefault("OFFLINE_MODE", "true")
    os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", "BOS")
    for directory in (
        root / "database",
        root / "workspace",
        root / "models" / "llm",
        root / "models" / "ollama",
        root / "local_knowledge",
        root / "logs",
        root / "runtime" / "paddlex-cache",
    ):
        directory.mkdir(parents=True, exist_ok=True)
    return root


def _url_available(url: str, timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 500
    except Exception:
        return False


def _port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as stream:
        stream.settimeout(0.5)
        return stream.connect_ex((host, port)) == 0


def _child_command(service: str) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, f"--{service}-service"]
    return [sys.executable, "-m", "app.native_launcher", f"--{service}-service"]


def _child_working_directory(root: Path) -> Path:
    return root if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]


def _configure_paddle_home(root: Path, environment: dict[str, str] | None = None) -> dict[str, str]:
    target = environment if environment is not None else os.environ
    target["USERPROFILE"] = str(root / "runtime" / "paddle-home")
    target["PADDLE_HOME"] = str(root / "runtime" / "paddle-home" / ".cache" / "paddle")
    return target


def _spawn(command: list[str], *, env: dict[str, str] | None = None, cwd: Path | None = None) -> subprocess.Popen:
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    return subprocess.Popen(command, env=env, cwd=cwd, creationflags=flags)


def _find_ollama(root: Path) -> Path | None:
    candidates = [
        root / "runtime" / "ollama" / "ollama.exe",
        root / "ollama" / "ollama.exe",
    ]
    installed = shutil.which("ollama.exe") or shutil.which("ollama")
    if installed:
        candidates.append(Path(installed))
    return next((item.resolve() for item in candidates if item.is_file()), None)


def ensure_ollama(root: Path) -> subprocess.Popen | None:
    if _url_available(f"http://{APP_HOST}:{OLLAMA_PORT}/api/tags"):
        return None
    executable = _find_ollama(root)
    if executable is None:
        return None
    environment = os.environ.copy()
    environment.setdefault("OLLAMA_HOST", f"{APP_HOST}:{OLLAMA_PORT}")
    environment.setdefault("OLLAMA_MODELS", str(root / "models" / "ollama"))
    environment.setdefault("OLLAMA_FLASH_ATTENTION", "1")
    environment.setdefault("OLLAMA_KEEP_ALIVE", "-1")
    process = _spawn([str(executable), "serve"], env=environment, cwd=executable.parent)
    _wait_for(f"http://{APP_HOST}:{OLLAMA_PORT}/api/tags", timeout=30)
    return process


def _wait_for(url: str, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _url_available(url):
            return True
        time.sleep(0.25)
    return False


def ensure_ocr(root: Path) -> subprocess.Popen | None:
    if _url_available(f"http://{APP_HOST}:{OCR_PORT}/health"):
        return None
    environment = _configure_paddle_home(root, os.environ.copy())
    process = _spawn(_child_command("ocr"), env=environment, cwd=_child_working_directory(root))
    if not _wait_for(f"http://{APP_HOST}:{OCR_PORT}/health", timeout=90):
        process.terminate()
        raise RuntimeError("PaddleOCR 本地服务启动失败")
    return process


def _terminate(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()


def run_ocr_service() -> None:
    root = _portable_root()
    _configure_paddle_home(root)
    import uvicorn

    uvicorn.run("ocr.service:app", host=APP_HOST, port=OCR_PORT, log_level="warning")


def run_ocr_self_test() -> int:
    _configure_paddle_home(_portable_root())
    import numpy as np
    from PIL import Image, ImageDraw

    from ocr.service import get_engine

    image = Image.new("RGB", (480, 120), "white")
    ImageDraw.Draw(image).text((24, 40), "HER2 2+  Ki-67 30%", fill="black")
    results = list(get_engine().predict(np.asarray(image)))
    print(f"PaddleOCR inference self-test passed: {len(results)} result(s)")
    return 0


def run_app_service(port: int) -> None:
    import uvicorn

    uvicorn.run("app.main:app", host=APP_HOST, port=port, log_level="info")


def run_launcher(port: int) -> int:
    root = configure_native_environment()
    app_url = f"http://{APP_HOST}:{port}"
    if _url_available(f"{app_url}/api/health"):
        webbrowser.open(app_url)
        return 0
    if _port_available(APP_HOST, port):
        raise RuntimeError(f"端口 {port} 已被其他程序占用")

    ocr_process: subprocess.Popen | None = None
    ollama_process: subprocess.Popen | None = None
    try:
        print("正在启动本地 OCR…")
        ocr_process = ensure_ocr(root)
        print("正在检测 Ollama…")
        ollama_process = ensure_ollama(root)
        if not _url_available(f"http://{APP_HOST}:{OLLAMA_PORT}/api/tags"):
            print("未检测到 Ollama；主程序仍会启动，可稍后放入或安装 Ollama runtime。")
        threading.Thread(
            target=lambda: (_wait_for(f"{app_url}/api/health", 60) and webbrowser.open(app_url)),
            daemon=True,
        ).start()
        print(f"Breast Cancer Extractor: {app_url}")
        print("关闭此窗口或按 Ctrl+C 可停止本次 Windows Native 服务。")
        run_app_service(port)
        return 0
    finally:
        _terminate(ocr_process)
        _terminate(ollama_process)


def run_smoke_test(port: int) -> int:
    root = configure_native_environment()
    ocr_process: subprocess.Popen | None = None
    ollama_process: subprocess.Popen | None = None
    app_process: subprocess.Popen | None = None
    try:
        ocr_process = ensure_ocr(root)
        ollama_process = ensure_ollama(root)
        app_process = _spawn(
            [*_child_command("app"), "--port", str(port)],
            env=os.environ.copy(),
            cwd=_child_working_directory(root),
        )
        health_url = f"http://{APP_HOST}:{port}/api/health"
        if not _wait_for(health_url, timeout=60):
            raise RuntimeError("Windows Native 主程序健康检查超时")
        with urllib.request.urlopen(health_url, timeout=10) as response:
            health = json.loads(response.read().decode("utf-8"))
        if health.get("status") != "ok" or not health.get("ocr", {}).get("available"):
            raise RuntimeError(f"Windows Native 健康检查失败：{health}")
        print(json.dumps(health, ensure_ascii=False, indent=2))
        return 0
    finally:
        _terminate(app_process)
        _terminate(ocr_process)
        _terminate(ollama_process)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ocr-service", action="store_true")
    parser.add_argument("--app-service", action="store_true")
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--ocr-self-test", action="store_true")
    parser.add_argument("--port", type=int, default=int(os.getenv("APP_PORT", DEFAULT_APP_PORT)))
    arguments = parser.parse_args()
    configure_native_environment()
    if arguments.ocr_service:
        run_ocr_service()
        return 0
    if arguments.app_service:
        run_app_service(arguments.port)
        return 0
    if arguments.smoke_test:
        return run_smoke_test(arguments.port)
    if arguments.ocr_self_test:
        return run_ocr_self_test()
    return run_launcher(arguments.port)


if __name__ == "__main__":
    raise SystemExit(main())
