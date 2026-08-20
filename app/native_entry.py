from __future__ import annotations

import secrets
import threading
from urllib.parse import parse_qs

from app import native_launcher as launcher


_shutdown_token: str | None = None
_original_start_shutdown_control = launcher._start_shutdown_control


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
    ``connect-src 'self'`` CSP.  The event is set only after the complete HTTP
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


def _run_app_service(port: int, shutdown_event: threading.Event | None = None) -> None:
    import uvicorn

    from app.main import app as downstream

    application = downstream
    if shutdown_event is not None and _shutdown_token:
        application = _native_shutdown_app(downstream, shutdown_event, _shutdown_token)

    config = uvicorn.Config(application, host=launcher.APP_HOST, port=port, log_level="info")
    server = uvicorn.Server(config)
    if shutdown_event is not None:
        def stop_when_requested() -> None:
            shutdown_event.wait()
            server.should_exit = True

        threading.Thread(target=stop_when_requested, name="bce-app-shutdown", daemon=True).start()
    server.run()


def main() -> int:
    # Patch only the Windows-native/Portable entry process. Child OCR/app-service
    # modes and the reusable launcher module keep their existing interfaces.
    launcher._start_shutdown_control = _capture_shutdown_control
    launcher.run_app_service = _run_app_service
    return launcher.main()


if __name__ == "__main__":
    raise SystemExit(main())
