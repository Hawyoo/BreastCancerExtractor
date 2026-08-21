import threading
from pathlib import Path

from app import native_entry
from app.native_entry import _is_service_invocation, _log_role


ROOT = Path(__file__).parents[1]


def test_service_children_do_not_use_the_portable_startup_window():
    assert _is_service_invocation(["--ocr-service"])
    assert _is_service_invocation(["--app-service"])
    assert _is_service_invocation(["--ocr-self-test"])
    assert _is_service_invocation(["--smoke-test"])
    assert not _is_service_invocation(["--port", "8765"])


def test_frozen_logs_are_split_by_process_role():
    assert _log_role([]) == "launcher"
    assert _log_role(["--ocr-service"]) == "ocr-service"
    assert _log_role(["--app-service"]) == "app-service"
    assert _log_role(["--ocr-self-test"]) == "ocr-self-test"


def test_portable_entry_reports_real_startup_stages_and_logs_output():
    source = (ROOT / "app" / "native_entry.py").read_text(encoding="utf-8")
    assert "PortableStartupWindow" in source
    assert 'log_dir = root / "logs"' in source
    assert 'sys.stdout = stream' in source
    assert 'sys.stderr = stream' in source
    for message in (
        "正在准备运行环境…",
        "正在启动本地 OCR…",
        "正在检查本地 AI / Ollama…",
        "正在启动 Web 服务…",
        "正在打开浏览器…",
    ):
        assert message in source


def test_startup_window_becomes_persistent_runtime_control_panel():
    source = (ROOT / "app" / "startup_window.py").read_text(encoding="utf-8")
    entry = (ROOT / "app" / "native_entry.py").read_text(encoding="utf-8")

    assert "✓ 系统已启动" in source
    assert 'text="重新打开浏览器"' in source
    assert 'text="关闭程序"' in source
    assert 'root.protocol("WM_DELETE_WINDOW", request_shutdown)' in source
    assert "浏览器可以安全关闭" not in source
    assert "on_reopen=_request_reopen_browser" in entry
    assert "on_shutdown=_request_full_shutdown" in entry
    assert '_startup_window.ready("✓ 系统已启动")' in entry
    assert "_startup_window.close()" not in entry.split("def _open_browser_with_status", 1)[1].split("def _run_app_service", 1)[0]


def test_runtime_control_reopens_the_saved_browser_url(monkeypatch):
    opened = []
    monkeypatch.setattr(native_entry, "_browser_url", "http://127.0.0.1:8765#token")
    monkeypatch.setattr(native_entry, "_original_webbrowser_open", lambda url: opened.append(url) or True)

    assert native_entry._request_reopen_browser()
    assert opened == ["http://127.0.0.1:8765#token"]


def test_runtime_control_close_button_and_window_x_use_launcher_shutdown(monkeypatch):
    launcher_event = threading.Event()
    requested = threading.Event()
    closing_calls = []

    class FakeWindow:
        def closing(self):
            closing_calls.append(True)

    monkeypatch.setattr(native_entry, "_launcher_shutdown_event", launcher_event)
    monkeypatch.setattr(native_entry, "_shutdown_requested", requested)
    monkeypatch.setattr(native_entry, "_startup_window", FakeWindow())

    native_entry._request_full_shutdown()

    assert requested.is_set()
    assert launcher_event.is_set()
    assert closing_calls == [True]


def test_startup_window_has_indeterminate_progress_and_first_run_hint():
    source = (ROOT / "app" / "startup_window.py").read_text(encoding="utf-8")
    assert 'mode="indeterminate"' in source
    assert "正在启动，请稍候…" in source
    assert "首次启动或首次加载 OCR 时可能需要更长时间" in source
    assert "启动失败" in source
    assert "详细日志" in source
