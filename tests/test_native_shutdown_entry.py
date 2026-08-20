import asyncio
import json
import threading
from pathlib import Path

from app.native_entry import _native_shutdown_app


async def _call(application, *, token: str, path: str = "/api/native/shutdown", method: str = "POST"):
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": f"token={token}".encode("utf-8"),
    }
    await application(scope, receive, send)
    return messages


def test_same_origin_shutdown_sends_success_before_signalling_exit():
    event = threading.Event()
    order = []

    class RecordingEvent:
        def set(self):
            order.append("event")
            event.set()

    async def downstream(scope, receive, send):
        raise AssertionError("native shutdown route unexpectedly reached downstream app")

    async def exercise():
        app = _native_shutdown_app(downstream, RecordingEvent(), "secret-token")
        messages = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)
            if message["type"] == "http.response.body":
                order.append("response")

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/native/shutdown",
            "query_string": b"token=secret-token",
        }
        await app(scope, receive, send)
        return messages

    messages = asyncio.run(exercise())
    assert messages[0]["status"] == 200
    assert json.loads(messages[1]["body"].decode("utf-8")) == {"status": "shutting_down"}
    assert order == ["response", "event"]
    assert event.is_set()


def test_same_origin_shutdown_rejects_wrong_token_without_exit_signal():
    event = threading.Event()

    async def downstream(scope, receive, send):
        raise AssertionError("native shutdown route unexpectedly reached downstream app")

    app = _native_shutdown_app(downstream, event, "secret-token")
    messages = asyncio.run(_call(app, token="wrong-token"))
    assert messages[0]["status"] == 403
    assert not event.is_set()


def test_non_shutdown_requests_still_reach_fastapi_app():
    event = threading.Event()
    reached = []

    async def downstream(scope, receive, send):
        reached.append(scope["path"])
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    app = _native_shutdown_app(downstream, event, "secret-token")
    messages = asyncio.run(_call(app, token="secret-token", path="/api/health", method="GET"))
    assert reached == ["/api/health"]
    assert messages[0]["status"] == 204
    assert not event.is_set()


def test_windows_native_and_portable_both_use_native_entrypoint():
    root = Path(__file__).parents[1]
    powershell = (root / "scripts" / "start-native.ps1").read_text(encoding="utf-8")
    spec = (root / "BreastCancerExtractor.spec").read_text(encoding="utf-8")
    assert "python -m app.native_entry" in powershell
    assert 'root / "app" / "native_entry.py"' in spec
    assert "console=False" in spec
    assert '"tkinter"' in spec
    assert '"tkinter.ttk"' in spec
