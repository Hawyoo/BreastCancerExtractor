import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    """Directory containing bundled read-only application resources."""
    if is_frozen():
        return Path(sys._MEIPASS).resolve()
    return Path(__file__).resolve().parents[1]


def portable_root() -> Path:
    """Writable root beside the executable (or repository root in development)."""
    configured = os.getenv("BCE_PORTABLE_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def portable_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else portable_root() / path
