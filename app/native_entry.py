from __future__ import annotations

import os
import secrets
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs

from app import native_launcher as launcher
from app.startup_window import PortableStartupWindow


_shutdown_token: str | None = None
_startup_window: PortableStartupWindow | None = None
_startup_complete = False
_startup_failed = False
_original_start_shutdown_control = launcher._start_shutdown_control
_original_ensure_ocr = launcher.ensure_ocr
_original_ensure_ollama = launcher.ensure_ollama
_original_webbrowser_open = launcher.webbrowser.open

_SERVICE_FLAGS = {
    "--ocr-service",
    "--app-service",
    "--smoke-test",
    "--ocr-self-test",
}


def _capture_shutdown_control(
    root,
    app_port: int,
    shutdown_event: threading.Event,
):
    """Start the existing fallback control server and retain this launch token."""
    global _shutdown_token
    server, control = _original_start_shutdown_control(root, app_port, shutdown_event)
    _shutdown_token = str(control["token"])
    return server, control


def _native_shutdown_app(downstream, shutdown_event: threading.Event, token: str):
    """Expose a token-protected shutdown endpoint on the app's own origin.

    The browser can fetch this route without weakening the application's
    ``connect-src 'self'`` CSP. The event is set only after the complete HTTP
    200 response has been handed to Uvicorn, so the page never reports a
    successful close before the launcher has actually accepted the request.
    """

    async def application(scope, receive, send):
        if scope.get("type") != "http" or scope.get("path") != "/api/native/shutdown":
            await downstream(scope, receive, send)
            return

        supplied = parse_qs(scope.get("query_string", b"").decode("utf-8", "replace")).get("token", [""])[0]
        authorized = (
            scope.get("method") == "POST"
            and bool(token)
            and secrets.compare_digest(str(supplied), token)
        )
        body = b'{"status":"shutting_down"}' if authorized else b'{"detail":"forbidden"}'
        status = 200 if authorized else 403
        headers = [
            (b"content-type", b"application/json; charset=utf-8"),
            (b"cache-control", b"no-store"),
            (b"content-length", str(len(body)).encode("ascii")),
        ]
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body, "more_body": False})
        if authorized:
            shutdown_event.set()

    return application


def _set_startup_status(message: str) -> None:
    if _startup_window is not None:
        _startup_window.update(message)


def _ensure_ocr_with_status(*args, **kwargs):
    _set_startup_status("正在启动本地 OCR…")
    return _original_ensure_ocr(*args, **kwargs)


def _ensure_ollama_with_status(*args, **kwargs):
    _set_startup_status("正在检查本地 AI / Ollama…")
    return _original_ensure_ollama(*args, **kwargs)


def _open_browser_with_status(url: str, *args, **kwargs):
    global _startup_complete, _startup_failed
    _set_startup_status("正在打开浏览器…")
    opened = _original_webbrowser_open(url, *args, **kwargs)
    if opened is False:
        _startup_failed = True
        if _startup_window is not None:
            _startup_window.fail("浏览器未能自动打开；程序仍在本地运行。")
    else:
        _startup_complete = True
        if _startup_window is not None:
            _startup_window.close()
    return opened


def _run_app_service(port: int, shutdown_event: threading.Event | None = None) -> None:
    import uvicorn

    from app.main import app as downstream

    application = downstream
    if shutdown_event is not None and _shutdown_token:
        application = _native_shutdown_app(downstream, shutdown_event, _shutdown_token)

    _set_startup_status("正在启动 Web 服务…")
    config = uvicorn.Config(application, host=launcher.APP_HOST, port=port, log_level="info")
    server = uvicorn.Server(config)
    if shutdown_event is not None:
        def stop_when_requested() -> None:
            shutdown_event.wait()
            server.should_exit = True

        threading.Thread(target=stop_when_requested, name="bce-app-shutdown", daemon=True).start()
    server.run()


def _is_service_invocation(arguments: list[str] | None = None) -> bool:
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    return any(flag in arguments for flag in _SERVICE_FLAGS)


def _is_frozen_windows() -> bool:
    return os.name == "nt" and bool(getattr(sys, "frozen", False))


def _log_role(arguments: list[str] | None = None) -> str:
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    if "--ocr-service" in arguments:
        return "ocr-service"
    if "--app-service" in arguments:
        return "app-service"
    if "--ocr-self-test" in arguments:
        return "ocr-self-test"
    if "--smoke-test" in arguments:
        return "smoke-test"
    return "launcher"


def _configure_frozen_logging() -> Path | None:
    """Give windowed PyInstaller processes a real stdout/stderr destination."""
    if not _is_frozen_windows():
        return None
    root = launcher.configure_native_environment()
    log_dir = root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{_log_role()}.log"
    stream = log_path.open("a", encoding="utf-8", buffering=1)
    sys.stdout = stream
    sys.stderr = stream
    print()
    print(f"[{datetime.now().isoformat(timespec='seconds')}] Breast Cancer Extractor process started")
    print(f"argv={sys.argv!r}")
    return log_path


def _install_startup_hooks() -> None:
    launcher.ensure_ocr = _ensure_ocr_with_status
    launcher.ensure_ollama = _ensure_ollama_with_status
    launcher.webbrowser.open = _open_browser_with_status


def main() -> int:
    global _startup_window

    log_path = _configure_frozen_logging()
    portable_gui = _is_frozen_windows() and not _is_service_invocation()
    if portable_gui and log_path is not None:
        _startup_window = PortableStartupWindow(log_path)
        _startup_window.start()
        _set_startup_status("正在准备运行环境…")
        _install_startup_hooks()

    # Patch only the Windows-native/Portable entry process. Child OCR/app-service
    # modes and the reusable launcher module keep their existing interfaces.
    launcher._start_shutdown_control = _capture_shutdown_control
    launcher.run_app_service = _run_app_service

    try:
        result = launcher.main()
        if portable_gui and _startup_window is not None and not _startup_complete:
            if _startup_failed:
                _startup_window.wait_closed()
            else:
                _startup_window.close()
        return result
    except Exception as exc:
        traceback.print_exc()
        if portable_gui and _startup_window is not None and not _startup_complete:
            _startup_window.fail(f"启动失败：{exc}")
            _startup_window.wait_closed()
            return 1
        raise


if __name__ == "__main__":
    raise SystemExit(main())
