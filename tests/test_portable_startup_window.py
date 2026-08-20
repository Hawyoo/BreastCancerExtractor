from pathlib import Path

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


def test_startup_window_closes_on_browser_open_and_stays_for_startup_error():
    source = (ROOT / "app" / "native_entry.py").read_text(encoding="utf-8")
    assert "_startup_window.close()" in source
    assert "_startup_window.fail(" in source
    assert "_startup_window.wait_closed()" in source
    assert "if portable_gui and _startup_window is not None and not _startup_complete" in source


def test_startup_window_has_indeterminate_progress_and_first_run_hint():
    source = (ROOT / "app" / "startup_window.py").read_text(encoding="utf-8")
    assert 'mode="indeterminate"' in source
    assert "正在启动，请稍候…" in source
    assert "首次启动或首次加载 OCR 时可能需要更长时间" in source
    assert "启动失败" in source
    assert "详细日志" in source
