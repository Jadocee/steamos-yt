"""The systemd user timer that keeps the apps NonSteamApps installed up to date."""

from __future__ import annotations

import shutil
import subprocess

from . import ui
from .config import Paths
from .fsutil import atomic_write_bytes

UNIT = "nonsteamapps-update"


def _systemctl(*args: str) -> bool:
    try:
        return subprocess.run(
            ["systemctl", "--user", *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode == 0
    except OSError:
        return False


def install(paths: Paths) -> None:
    if not shutil.which("systemctl"):
        ui.warn(f"systemd is not available, so apps will not update automatically; run '{paths.launcher} update' now and then")
        return
    templates = paths.program / "share" / "systemd"
    service = (templates / f"{UNIT}.service").read_text(encoding="utf-8").replace("@LAUNCHER@", str(paths.launcher))
    atomic_write_bytes(paths.systemd / f"{UNIT}.service", service.encode("utf-8"))
    atomic_write_bytes(paths.systemd / f"{UNIT}.timer", (templates / f"{UNIT}.timer").read_bytes())
    if _systemctl("daemon-reload") and _systemctl("enable", "--now", f"{UNIT}.timer"):
        ui.ok(f"Enabled weekly app updates ({UNIT}.timer)")
    else:
        ui.warn(f"could not enable {UNIT}.timer (no systemd user session?); run '{paths.launcher} update' now and then")


def remove(paths: Paths) -> None:
    files = [paths.systemd / f"{UNIT}.service", paths.systemd / f"{UNIT}.timer"]
    if not any(path.exists() for path in files):
        return
    if shutil.which("systemctl"):
        _systemctl("disable", "--now", f"{UNIT}.timer")
    for path in files:
        path.unlink(missing_ok=True)
    if shutil.which("systemctl"):
        _systemctl("daemon-reload")


def status(paths: Paths) -> str:
    if not (paths.systemd / f"{UNIT}.timer").exists():
        return "not installed"
    if not shutil.which("systemctl"):
        return "installed (systemd unavailable)"
    try:
        state = subprocess.run(
            ["systemctl", "--user", "is-enabled", f"{UNIT}.timer"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
    except OSError:
        state = ""
    return f"weekly ({state or 'unknown'})"
