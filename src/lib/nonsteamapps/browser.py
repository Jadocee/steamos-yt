"""Console set-up for the apps that run in Helium.

Each app keeps one Helium profile per Steam account. Before every start, the
profile is told it closed cleanly (Steam ends apps by signalling them) and that
first-run pages are done. Arrow keys move between links and buttons (spatial
navigation), Helium and sites that offer a dark theme start dark (Helium's
Mode setting can still choose light), and in Game Mode the interface scales
with the screen, so a TV reads like a TV app.

Helium already blocks ads (uBlock Origin), third-party cookies and WebRTC's
local addresses, adds fingerprinting noise and keeps background mode, link
auditing and preloading off; new profiles also send Global Privacy Control
and do not keep crash reports to offer for upload.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

from .fsutil import atomic_write_bytes, atomic_write_json

BLOCK = 2
SCHEMA_VERSION = 1
CRASH_REPORTS_OFF = -1
FEATURES = "AcceleratedVideoDecodeLinuxGL,AcceleratedVideoDecodeLinuxZeroCopyGL"
TV_HEIGHT = 720
BROWSER_BINARIES = ("helium", "chrome", "chromium")
_SCREEN = re.compile(r"current (\d+) x (\d+)")


def deep_merge(base: dict, overlay: dict) -> dict:
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def first_run_preferences(kiosk: bool) -> dict:
    """Written once, into a new profile: Global Privacy Control, no notification requests, and for full-screen apps no other prompts."""
    preferences: dict = {
        "helium": {"global_privacy_control": True},
        "browser": {"has_seen_welcome_page": True},
        "profile": {"default_content_setting_values": {"notifications": BLOCK}},
    }
    if kiosk:
        deep_merge(preferences, {
            "translate": {"enabled": False},
            "credentials_enable_service": False,
            "credentials_enable_autosignin": False,
            "autofill": {"profile_enabled": False, "credit_card_enabled": False},
            "profile": {"password_manager_enabled": False, "default_content_setting_values": {"geolocation": BLOCK}},
        })
    return preferences


def launch_preferences(services: bool) -> dict:
    """Applied before every start: onboarding done, the services choice, and a clean last exit."""
    helium: dict = {"completed_onboarding": True, "services": {"enabled": services}}
    if services:
        helium["services"]["user_consented"] = True
    return {
        "helium": helium,
        "browser": {"has_seen_welcome_page": True},
        "profile": {"exit_type": "Normal", "exited_cleanly": True},
    }


def _load(path: Path) -> Optional[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def write_preferences(profile: Path, services: bool, kiosk: bool) -> Path:
    path = Path(profile) / "Default" / "Preferences"
    fresh = not path.exists()
    data = _load(path)
    if data is None:
        atomic_write_bytes(path.with_name("Preferences.corrupt"), path.read_bytes())
        data, fresh = {}, True
    if fresh:
        deep_merge(data, first_run_preferences(kiosk))
    deep_merge(data, launch_preferences(services))
    if services:
        settings = data["helium"]["services"]
        if not isinstance(settings.get("schema_version"), int) or settings["schema_version"] < SCHEMA_VERSION:
            settings["schema_version"] = SCHEMA_VERSION
    atomic_write_json(path, data, compact=True)
    return path


def write_local_state(profile: Path) -> Path:
    """Start a new profile with crash reports off, so no upload question follows a crash; later starts keep the user's choice."""
    path = Path(profile) / "Local State"
    if not path.exists():
        atomic_write_json(path, {"helium": {"crash_reporting": {"mode": CRASH_REPORTS_OFF}}}, compact=True)
    return path


def clear_stale_lock(profile: Path) -> bool:
    """Remove a lock left by a Helium that is no longer running, which would block the next start."""
    lock = Path(profile) / "SingletonLock"
    try:
        target = os.readlink(lock)
    except OSError:
        return False
    pid = target.rsplit("-", 1)[-1]
    if pid.isdecimal():
        try:
            exe = os.path.basename(os.readlink(f"/proc/{pid}/exe")).replace(" (deleted)", "")
        except OSError:
            exe = ""
        if exe in BROWSER_BINARIES:
            return False
    for name in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        path = Path(profile) / name
        if path.is_symlink() or path.exists():
            path.unlink()
    return True


def link_widevine(profile: Path, shared: Path) -> None:
    """Point the profile's Widevine folder at one shared by every profile, so one download serves them all."""
    Path(shared).mkdir(parents=True, exist_ok=True)
    link = Path(profile) / "WidevineCdm"
    if link.is_symlink() and not link.exists():
        link.unlink()
    if not link.exists():
        link.symlink_to(shared, target_is_directory=True)


def prepare(profile: Path, services: bool, kiosk: bool, widevine: Path) -> None:
    Path(profile).mkdir(parents=True, exist_ok=True)
    write_preferences(profile, services, kiosk)
    write_local_state(profile)
    clear_stale_lock(profile)
    link_widevine(profile, widevine)


def screen_height() -> Optional[int]:
    if not os.environ.get("DISPLAY") or not shutil.which("xrandr"):
        return None
    try:
        output = subprocess.run(
            ["xrandr", "--current"], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=5, check=False
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = _SCREEN.search(output)
    return int(match.group(2)) if match else None


def scale(setting: str, game_mode: bool, height: Optional[int] = None) -> Optional[float]:
    """The interface scale: a number from the settings, or in Game Mode one that shows a 720p-sized layout."""
    value = (setting or "auto").strip().lower()
    if value != "auto":
        try:
            number = float(value)
        except ValueError:
            return None
        return min(max(number, 0.5), 4.0) if number != 1 else None
    if not game_mode:
        return None
    height = screen_height() if height is None else height
    if not height or height < 1000:
        return None
    return round(height / TV_HEIGHT * 4) / 4


def flags(profile: Path, url: str, kiosk: bool, game_mode: bool, factor: Optional[float], name: str) -> List[str]:
    arguments = [
        f"--user-data-dir={profile}",
        f"--class={name}",
        "--no-first-run",
        "--no-default-browser-check",
        "--password-store=basic",
        "--hide-crash-restore-bubble",
        "--noerrdialogs",
        "--enable-spatial-navigation",
        "--force-dark-mode",
        f"--enable-features={FEATURES}",
        "--ozone-platform=x11" if game_mode else "--ozone-platform-hint=auto",
    ]
    if factor:
        arguments.append(f"--force-device-scale-factor={factor:g}")
    if kiosk:
        arguments += [
            "--kiosk",
            "--autoplay-policy=no-user-gesture-required",
            "--deny-permission-prompts",
            "--disable-pinch",
            "--overscroll-history-navigation=0",
        ]
    else:
        arguments.append("--start-maximized")
    return arguments + ([url] if url else [])
