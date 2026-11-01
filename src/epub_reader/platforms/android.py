"""Android integration without JNI: the Java MainActivity exchanges small files with Python.

Everything here is a no-op off Android. ``content://`` documents are read with QFile, which
Qt resolves through the Android ContentResolver.
"""

import logging
import os
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QFile, QIODevice

logger = logging.getLogger(__name__)

IS_ANDROID = "ANDROID_ARGUMENT" in os.environ


def _private_dir() -> Path:
    return Path(os.environ["ANDROID_PRIVATE"])


def stage_content_uri(uri: str) -> tuple[Path, Callable[[], None]]:
    """Copy a content:// document to a temporary .epub file; return it and a cleanup callback."""
    folder = Path(tempfile.mkdtemp(prefix="epubify-open-"))
    target = folder / "book.epub"
    source = QFile(uri)
    try:
        if not source.open(QIODevice.OpenModeFlag.ReadOnly):
            raise ValueError("Unable to read the selected file.")
        with target.open("wb") as output:
            while chunk := source.read(64 * 1024):
                output.write(bytes(chunk.data()))
        return target, lambda: shutil.rmtree(folder, ignore_errors=True)
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    finally:
        source.close()


def take_intent_uri() -> str | None:
    """Return the document URI another app asked us to open, once."""
    if not IS_ANDROID:
        return None
    pending = _private_dir() / "open-intent.txt"
    try:
        uri = pending.read_text(encoding="utf-8").strip()
        pending.unlink()
    except FileNotFoundError:
        return None
    except OSError:
        logger.exception("Unable to read the pending document")
        return None
    return uri or None


def set_system_bars(color: str, *, dark: bool) -> None:
    """Ask MainActivity to paint the status/navigation bars and pick icon contrast."""
    if not IS_ANDROID:
        return
    try:
        target = _private_dir() / "system-bars.txt"
        partial = target.with_suffix(".tmp")
        partial.write_text(f"{color} {'dark' if dark else 'light'}\n", encoding="utf-8")
        partial.replace(target)
    except OSError:
        logger.exception("Unable to color the system bars")
