from __future__ import annotations

import os
import queue
import threading
import traceback
from pathlib import Path
from typing import Callable


class PortableStartupWindow:
    """Small Windows-only startup and runtime control window.

    The UI runs on its own Tk message-loop thread so OCR / Ollama / Uvicorn
    startup can remain synchronous in the launcher thread. After startup it
    remains available as a small control panel for reopening the browser or
    shutting down the whole Portable process tree.
    """

    def __init__(
        self,
        log_path: Path,
        *,
        on_reopen: Callable[[], bool] | None = None,
        on_shutdown: Callable[[], None] | None = None,
        icon_path: Path | None = None,
    ) -> None:
        self.log_path = Path(log_path)
        self.on_reopen = on_reopen
        self.on_shutdown = on_shutdown
        self.icon_path = Path(icon_path) if icon_path else Path(__file__).resolve().parent / "static" / "favicon.ico"
        self._commands: queue.Queue[tuple[str, str | None]] = queue.Queue()
        self._started = threading.Event()
        self._closed = threading.Event()
        self._thread: threading.Thread | None = None
        self._running = False
        self._failed = False

    @property
    def running(self) -> bool:
        return self._running and not self._closed.is_set()

    @property
    def failed(self) -> bool:
        return self._failed

    def start(self) -> None:
        if os.name != "nt" or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="bce-startup-window", daemon=True)
        self._thread.start()
        self._started.wait(timeout=3)

    def update(self, message: str) -> None:
        if self.running:
            self._commands.put(("status", str(message)))

    def ready(self, message: str = "✓ 系统已启动") -> None:
        if self.running:
            self._commands.put(("ready", str(message)))

    def closing(self) -> None:
        if self.running:
            self._commands.put(("closing", None))

    def close(self) -> None:
        if self.running:
            self._commands.put(("close", None))

    def fail(self, message: str) -> None:
        self._failed = True
        if self.running:
            self._commands.put(("error", str(message)))

    def wait_closed(self, timeout: float | None = None) -> bool:
        return self._closed.wait(timeout=timeout)

    def _run(self) -> None:
        try:
            import tkinter as tk
            from tkinter import ttk

            root = tk.Tk()
            self._running = True
            root.title("Breast Cancer Extractor")
            if self.icon_path.is_file():
                try:
                    root.iconbitmap(default=str(self.icon_path))
                except tk.TclError:
                    # The window remains usable if a non-Windows Tk runtime
                    # cannot decode the Windows ICO resource.
                    pass
            root.resizable(False, False)

            container = ttk.Frame(root, padding=(26, 22))
            container.pack(fill="both", expand=True)

            title = tk.Label(container, text="Breast Cancer Extractor", font=("Segoe UI", 16, "bold"), anchor="w")
            title.pack(fill="x")
            subtitle = tk.Label(container, text="正在启动，请稍候…", font=("Segoe UI", 10), anchor="w")
            subtitle.pack(fill="x", pady=(4, 14))

            status_var = tk.StringVar(value="正在准备运行环境…")
            status = tk.Label(container, textvariable=status_var, font=("Segoe UI", 10), anchor="w")
            status.pack(fill="x")

            progress = ttk.Progressbar(container, mode="indeterminate", length=390)
            progress.pack(fill="x", pady=(10, 12))
            progress.start(12)

            note_var = tk.StringVar(value="首次启动或首次加载 OCR 时可能需要更长时间")
            note = tk.Label(container, textvariable=note_var, font=("Segoe UI", 9), anchor="w", justify="left", wraplength=390)
            note.pack(fill="x")

            controls = ttk.Frame(container)
            reopen_button = ttk.Button(controls, text="重新打开浏览器")
            shutdown_button = ttk.Button(controls, text="关闭程序")
            reopen_button.pack(side="left", padx=(0, 10))
            shutdown_button.pack(side="left")

            state = {"mode": "starting", "shutdown_requested": False}

            def request_reopen() -> None:
                if state["mode"] != "ready" or self.on_reopen is None:
                    return
                try:
                    opened = self.on_reopen()
                except Exception:
                    opened = False
                    traceback.print_exc()
                if opened is False:
                    note_var.set("无法自动打开浏览器，请检查 Windows 默认浏览器设置。")
                else:
                    note_var.set("")

            def request_shutdown() -> None:
                if state["mode"] == "failed":
                    root.destroy()
                    return
                if state["shutdown_requested"]:
                    return
                state["shutdown_requested"] = True
                state["mode"] = "closing"
                progress.stop()
                if progress.winfo_manager():
                    progress.pack_forget()
                if controls.winfo_manager():
                    controls.pack_forget()
                subtitle.config(text="正在关闭程序…")
                status_var.set("正在停止后台服务，请稍候…")
                note_var.set("")
                root.lift()
                try:
                    if self.on_shutdown is not None:
                        self.on_shutdown()
                except Exception:
                    traceback.print_exc()

            reopen_button.configure(command=request_reopen)
            shutdown_button.configure(command=request_shutdown)
            root.protocol("WM_DELETE_WINDOW", request_shutdown)

            root.update_idletasks()
            width = 450
            height = max(190, root.winfo_reqheight())
            screen_w = root.winfo_screenwidth()
            screen_h = root.winfo_screenheight()
            x = max(0, (screen_w - width) // 2)
            y = max(0, (screen_h - height) // 3)
            root.geometry(f"{width}x{height}+{x}+{y}")
            root.lift()
            root.attributes("-topmost", True)
            root.after(900, lambda: root.attributes("-topmost", False))

            def show_ready(message: str) -> None:
                state["mode"] = "ready"
                progress.stop()
                if progress.winfo_manager():
                    progress.pack_forget()
                status_var.set("")
                note_var.set("")
                subtitle.config(text=message or "✓ 系统已启动")
                if not controls.winfo_manager():
                    controls.pack(fill="x", pady=(8, 0))
                root.update_idletasks()
                root.geometry(f"{width}x{max(155, root.winfo_reqheight())}+{x}+{y}")

            def show_error(message: str) -> None:
                state["mode"] = "failed"
                progress.stop()
                if progress.winfo_manager():
                    progress.pack_forget()
                if controls.winfo_manager():
                    controls.pack_forget()
                subtitle.config(text="启动失败")
                status_var.set(message or "启动失败")
                note_var.set(f"详细日志：{self.log_path}\n关闭此窗口退出。")
                root.lift()
                root.attributes("-topmost", True)

            def poll_commands() -> None:
                try:
                    while True:
                        command, payload = self._commands.get_nowait()
                        if command == "status" and state["mode"] == "starting":
                            status_var.set(payload or "正在启动…")
                        elif command == "ready":
                            show_ready(payload or "✓ 系统已启动")
                        elif command == "closing":
                            if not state["shutdown_requested"]:
                                state["shutdown_requested"] = True
                                state["mode"] = "closing"
                                progress.stop()
                                if progress.winfo_manager():
                                    progress.pack_forget()
                                if controls.winfo_manager():
                                    controls.pack_forget()
                                subtitle.config(text="正在关闭程序…")
                                status_var.set("正在停止后台服务，请稍候…")
                                note_var.set("")
                        elif command == "error":
                            show_error(payload or "启动失败")
                        elif command == "close":
                            root.destroy()
                            return
                except queue.Empty:
                    pass
                if root.winfo_exists():
                    root.after(80, poll_commands)

            self._started.set()
            root.after(80, poll_commands)
            root.mainloop()
        except Exception:
            # Startup UI is a usability layer, never a reason to prevent the
            # actual local application from launching. Persist the UI failure
            # so a windowed build still has a diagnosable startup record.
            try:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                with self.log_path.open("a", encoding="utf-8") as stream:
                    stream.write("\nStartup window failed:\n")
                    traceback.print_exc(file=stream)
            except OSError:
                pass
            self._started.set()
        finally:
            self._running = False
            self._closed.set()
