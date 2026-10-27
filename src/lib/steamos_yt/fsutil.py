"""Small filesystem helpers shared by the Steam and profile modules."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Replace ``path`` with ``data`` without ever leaving a partial file behind."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o7777 if path.exists() else 0o644
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def atomic_write_json(path: Path, value, compact: bool = False) -> None:
    if compact:
        text = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    else:
        text = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    atomic_write_bytes(path, text.encode("utf-8"))


def atomic_copy(source: Path, destination: Path) -> None:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=str(destination.parent))
    os.close(fd)
    try:
        shutil.copyfile(source, tmp)
        os.chmod(tmp, 0o644)
        os.replace(tmp, destination)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
