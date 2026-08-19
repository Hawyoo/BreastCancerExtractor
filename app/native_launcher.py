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


class _WindowsKillOnCloseJob:
    """Own child processes started by this launcher on Windows.

    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE is the important part: even when the
    console is closed or the launcher crashes before Python cleanup runs, the
    OS closes this process's job handle and terminates every process in the
    assigned child tree. External services that were already running are never
    assigned to this job and therefore are not affected.
    """

    def __init__(self) -> None:
        self.handle = None
        self._kernel32 = None
        if os.name != "nt":
            return
        import ctypes
        from ctypes import wintypes

        ULONG_PTR = ctypes.c_size_t
        SIZE_T = ctypes.c_size_t

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", SIZE_T),
                ("MaximumWorkingSetSize", SIZE_T),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ULONG_PTR),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_ulonglong),
                ("WriteOperationCount", ctypes.c_ulonglong),
                ("OtherOperationCount", ctypes.c_ulonglong),
                ("ReadTransferCount", ctypes.c_ulonglong),
                ("WriteTransferCount", ctypes.c_ulonglong),
                ("OtherTransferCount", ctypes.c_ulonglong),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", SIZE_T),
                ("JobMemoryLimit", SIZE_T),
                ("PeakProcessMemoryUsed", SIZE_T),
                ("PeakJobMemoryUsed", SIZE_T),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            error = ctypes.get_last_error()
            kernel32.CloseHandle(handle)
            raise OSError(error, "SetInformationJobObject failed")
        self.handle = handle
        self._kernel32 = kernel32

    def assign(self, process: subprocess.Popen) -> bool:
        if os.name != "nt" or self.handle is None or process.poll() is not None:
            return False
        import ctypes
        from ctypes import wintypes

        if self._kernel32.AssignProcessToJobObject(self.handle, wintypes.HANDLE(process._handle)):
            return True
        error = ctypes.get_last_error()
        print(f"警告：无法将子进程 {process.pid} 加入 Windows Job Object（错误 {error}）。")
        return False

    def close(self) -> None:
        if os.name == "nt" and self.handle is not None:
            self._kernel32.CloseHandle(self.handle)
            self.handle = None


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
    os.environ["DATA_PATH"] = str(root / "database")
    os.environ["CONFIG_PATH"] = str(root / "config")
    os.environ["RUNTIME_PATH"] = str(root / "runtime")
    os.environ["DATABASE_PATH"] = str(root / "runtime" / "catalog.sqlite")
    os.environ["MODEL_IMPORT_PATH"] = str(root / "models" / "llm")
    os.environ["OLLAMA_URL"] = f"http://{APP_HOST}:{OLLAMA_PORT}"
    os.environ["OCR_URL"] = f"http://{APP_HOST}:{OCR_PORT}"
    os.environ["PADDLE_PDX_CACHE_HOME"] = str(root / "runtime" / "paddlex-cache")
    os.environ.setdefault("OFFLINE_MODE", "true")
    os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", "BOS")
    for directory in (
        root / "database",
        root / "database" / "patients",
        root / "config",
        root / "runtime",
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


def _spawn(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
    job: _WindowsKillOnCloseJob | None = None,
) -> subprocess.Popen:
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    process = subprocess.Popen(command, env=env, cwd=cwd, creationflags=flags)
    if job is not None:
        job.assign(process)
    return process


def _find_ollama(root: Path) -> Path | None:
    candidates = [
        root / "runtime" / "ollama" / "ollama.exe",
        root / "ollama" / "ollama.exe",
    ]
    installed = shutil.which("ollama.exe") or shutil.which("ollama")
    if installed:
        candidates.append(Path(installed))
    return next((item.resolve() for item in candidates if item.is_file()), None)


def _runtime_config_file(root: Path) -> Path:
    target = root / "config" / "runtime_config.json"
    legacy = root / "database" / "runtime_config.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    if legacy.is_file():
        if not target.exists():
            legacy.replace(target)
        else:
            legacy.unlink(missing_ok=True)
    return target


def _ollama_disabled(root: Path) -> bool:
    config = _runtime_config_file(root)
    if not config.is_file():
        return False
    try:
        payload = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    return isinstance(payload, dict) and payload.get("ollama_provider") == "DISABLED"


def ensure_ollama(root: Path, job: _WindowsKillOnCloseJob | None = None) -> subprocess.Popen | None:
    # An already-running Ollama is external ownership: use it, but never assign
    # or terminate it when BreastCancerExtractor exits.
    if _url_available(f"http://{APP_HOST}:{OLLAMA_PORT}/api/tags"):
        return None
    if _ollama_disabled(root):
        return None
    executable = _find_ollama(root)
    if executable is None:
        return None
    environment = os.environ.copy()
    environment.setdefault("OLLAMA_HOST", f"{APP_HOST}:{OLLAMA_PORT}")
    environment.setdefault("OLLAMA_MODELS", str(root / "models" / "ollama"))
    environment.setdefault("OLLAMA_FLASH_ATTENTION", "1")
    environment.setdefault("OLLAMA_KEEP_ALIVE", "-1")
    process = _spawn([str(executable), "serve"], env=environment, cwd=executable.parent, job=job)
    _wait_for(f"http://{APP_HOST}:{OLLAMA_PORT}/api/tags", timeout=30)
    return process


def _wait_for(url: str, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _url_available(url):
            return True
        time.sleep(0.25)
    return False


def ensure_ocr(root: Path, job: _WindowsKillOnCloseJob | None = None) -> subprocess.Popen | None:
    if _url_available(f"http://{APP_HOST}:{OCR_PORT}/health"):
        return None
    environment = _configure_paddle_home(root, os.environ.copy())
    process = _spawn(_child_command("ocr"), env=environment, cwd=_child_working_directory(root), job=job)
    if not _wait_for(f"http://{APP_HOST}:{OCR_PORT}/health", timeout=90):
        _terminate(process)
        raise RuntimeError("PaddleOCR 本地服务启动失败")
    return process


def _terminate(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=8)
        return
    except subprocess.TimeoutExpired:
        pass
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    else:
        process.kill()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()


def _watch_ai_disconnect(root: Path, process: subprocess.Popen, stop_event: threading.Event) -> None:
    """Release only the Ollama process this launcher started when AI is disabled."""
    while not stop_event.wait(0.5):
        if process.poll() is not None:
            return
        if _ollama_disabled(root):
            print("已切换为仅 OCR 模式，正在停止本程序启动的 Ollama…")
            _terminate(process)
            return


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

    job = _WindowsKillOnCloseJob()
    ocr_process: subprocess.Popen | None = None
    ollama_process: subprocess.Popen | None = None
    watcher_stop = threading.Event()
    try:
        print("正在启动本地 OCR…")
        ocr_process = ensure_ocr(root, job=job)
        if _ollama_disabled(root):
            print("本地 AI 已断开：仅启动 OCR，不启动 Ollama。")
        else:
            print("正在检测 Ollama…")
            ollama_process = ensure_ollama(root, job=job)
            if not _url_available(f"http://{APP_HOST}:{OLLAMA_PORT}/api/tags"):
                print("未检测到 Ollama；主程序仍会启动，可使用仅 OCR 模式。")
            if ollama_process is not None:
                threading.Thread(
                    target=_watch_ai_disconnect,
                    args=(root, ollama_process, watcher_stop),
                    daemon=True,
                ).start()
        threading.Thread(
            target=lambda: (_wait_for(f"{app_url}/api/health", 60) and webbrowser.open(app_url)),
            daemon=True,
        ).start()
        print(f"Breast Cancer Extractor: {app_url}")
        print("关闭此窗口或按 Ctrl+C 将停止本程序启动的 OCR/Ollama 子进程树。")
        run_app_service(port)
        return 0
    finally:
        watcher_stop.set()
        _terminate(ocr_process)
        _terminate(ollama_process)
        # Closing this handle is the last-resort tree cleanup. It also covers
        # Ctrl+Close / abnormal launcher termination when finally cannot run.
        job.close()


def run_smoke_test(port: int) -> int:
    root = configure_native_environment()
    job = _WindowsKillOnCloseJob()
    ocr_process: subprocess.Popen | None = None
    ollama_process: subprocess.Popen | None = None
    app_process: subprocess.Popen | None = None
    try:
        ocr_process = ensure_ocr(root, job=job)
        ollama_process = ensure_ollama(root, job=job)
        app_process = _spawn(
            [*_child_command("app"), "--port", str(port)],
            env=os.environ.copy(),
            cwd=_child_working_directory(root),
            job=job,
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
        job.close()


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
