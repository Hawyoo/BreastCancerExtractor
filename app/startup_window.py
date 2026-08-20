from __future__ import annotations

import os
import queue
import threading
from pathlib import Path


class PortableStartupWindow:
    """Small Windows-only startup window for the frozen Portable executable.

    The UI runs on its own Tk message-loop thread so OCR / Ollama / Uvicorn
    startup can remain synchronous in the launcher thread.  Source-mode and
    non-Windows runs can simply skip creating this window.
    """

    def __init__(self, log_path: Path) -> None:
        self.log_path = Path(log_path)
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
            root.resizable(False, False)
            root.configure(padx=26, pady=22)

            title = tk.Label(root, text="Breast Cancer Extractor", font=("Segoe UI", 16, "bold"), anchor="w")
            title.pack(fill="x")
            subtitle = tk.Label(root, text="正在启动，请稍候…", font=("Segoe UI", 10), anchor="w")
            subtitle.pack(fill="x", pady=(4, 14))

            status_var = tk.StringVar(value="正在准备运行环境…")
            status = tk.Label(root, textvariable=status_var, font=("Segoe UI", 10), anchor="w")
            status.pack(fill="x")

            progress = ttk.Progressbar(root, mode="indeterminate", length=390)
            progress.pack(fill="x", pady=(10, 12))
            progress.start(12)

            note_var = tk.StringVar(value="首次启动或首次加载 OCR 时可能需要更长时间")
            note = tk.Label(root, textvariable=note_var, font=("Segoe UI", 9), anchor="w", justify="left", wraplength=390)
            note.pack(fill="x")

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

            allow_close = {"value": False}

            def on_close() -> None:
                if allow_close["value"]:
                    root.destroy()

            root.protocol("WM_DELETE_WINDOW", on_close)

            def poll_commands() -> None:
                try:
                    while True:
                        command, payload = self._commands.get_nowait()
                        if command == "status":
                            status_var.set(payload or "正在启动…")
                        elif command == "error":
                            allow_close["value"] = True
                            progress.stop()
                            subtitle.config(text="启动失败")
                            status_var.set(payload or "启动失败")
                            note_var.set(f"详细日志：{self.log_path}\n关闭此窗口退出。")
                            root.lift()
                            root.attributes("-topmost", True)
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
            # actual local application from launching. Detailed startup output
            # is still written to logs by native_entry.
            self._started.set()
        finally:
            self._running = False
            self._closed.set()
