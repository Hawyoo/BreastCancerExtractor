import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

from app.native_launcher import APP_HOST, _browser_control_url, _start_shutdown_control


def test_browser_control_url_keeps_token_in_fragment():
    url = _browser_control_url(
        "http://127.0.0.1:8765",
        {"port": 43123, "token": "secret-token"},
    )
    assert url == "http://127.0.0.1:8765#bce_control_port=43123&bce_shutdown_token=secret-token"


def test_shutdown_control_requires_token_and_signals(tmp_path):
    shutdown_event = threading.Event()
    server, control = _start_shutdown_control(tmp_path, 8765, shutdown_event)
    base = f"http://{APP_HOST}:{control['port']}/shutdown"
    try:
        bad = urllib.request.Request(
            f"{base}?token=wrong",
            method="POST",
            headers={"Origin": "http://127.0.0.1:8765"},
        )
        try:
            urllib.request.urlopen(bad, timeout=2)
        except urllib.error.HTTPError as exc:
            assert exc.code == 403
        else:
            raise AssertionError("shutdown control accepted an invalid token")
        assert not shutdown_event.is_set()

        good = urllib.request.Request(
            f"{base}?token={control['token']}",
            method="POST",
            headers={"Origin": "http://127.0.0.1:8765"},
        )
        with urllib.request.urlopen(good, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload == {"status": "shutting_down"}
        assert shutdown_event.wait(1)
    finally:
        server.shutdown()
        server.server_close()


def test_shutdown_button_is_windows_launcher_only():
    source = (Path(__file__).parents[1] / "app" / "static" / "shutdown.js").read_text(encoding="utf-8")
    assert "bce_control_port" in source
    assert "bce_shutdown_token" in source
    assert "关闭程序" in source
    assert "window.close()" in source
