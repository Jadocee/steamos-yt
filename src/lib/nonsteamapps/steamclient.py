"""Close and restart the Steam client around changes to its library files."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from . import ui

SHUTDOWN_TIMEOUT = 45.0


def running() -> bool:
    """Whether a Steam client process runs as the current user."""
    uid = os.getuid()
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            if entry.stat().st_uid == uid and (entry / "comm").read_text().strip() == "steam":
                return True
        except OSError:
            continue
    return False


def in_game_mode() -> bool:
    return os.environ.get("XDG_CURRENT_DESKTOP") == "gamescope" or bool(os.environ.get("GAMESCOPE_WAYLAND_DISPLAY"))


def command() -> Optional[str]:
    found = shutil.which("steam")
    if found:
        return found
    script = Path.home() / ".local/share/Steam/steam.sh"
    return str(script) if os.access(script, os.X_OK) else None


def _detach(args) -> None:
    subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def stop(retry: str) -> bool:
    """Close Steam if it runs, after asking; return whether it was closed. ``retry`` is the command to suggest."""
    if not running():
        return False
    if in_game_mode():
        raise ui.Abort(f"Steam is running in Game Mode and cannot be closed from here. Switch to Desktop Mode and run: {retry}")
    if not ui.confirm("Steam must be closed to update its library. Close Steam now?", default=True):
        raise ui.Abort(f"Steam was left running; close it and run: {retry}")
    ui.log("Closing Steam")
    steam = command()
    if steam:
        _detach([steam, "-shutdown"])
    elif shutil.which("xdg-open"):
        _detach(["xdg-open", "steam://exit"])
    deadline = time.monotonic() + SHUTDOWN_TIMEOUT
    while running():
        if time.monotonic() > deadline:
            raise ui.Abort(f"Steam did not close within {SHUTDOWN_TIMEOUT:.0f} seconds; close it manually and run: {retry}")
        time.sleep(0.5)
    time.sleep(1)
    return True


def start() -> None:
    steam = command()
    if not steam:
        ui.warn("could not find the steam command; start Steam manually")
        return
    ui.log("Starting Steam again")
    _detach([steam, "-silent"])


@contextmanager
def closed(retry: str, restart: bool = True) -> Iterator[None]:
    """Keep Steam closed for the duration of the block, then start it again if it was running."""
    stopped = stop(retry)
    try:
        yield
    finally:
        if stopped and restart:
            start()
