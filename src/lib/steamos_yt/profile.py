"""Create, seed and maintain the Helium profiles used by the kiosk (one per Steam account)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional

from .fsutil import atomic_write_bytes, atomic_write_json

BLOCK = 2
SHARED_PROFILE = "profile"
ACCOUNT_PROFILES = "profiles"
BROWSER_BINARIES = ("helium", "chrome", "chromium")
DELETED = " (deleted)"


def managed_preferences(services: bool = True) -> dict:
    """Preferences that keep a TV-style kiosk free of prompts, bubbles and first-run pages."""
    return {
        "helium": {
            "completed_onboarding": True,
            "services": {"user_consented": bool(services)},
        },
        "browser": {
            "has_seen_welcome_page": True,
            "enable_spellchecking": False,
        },
        "translate": {"enabled": False},
        "credentials_enable_service": False,
        "credentials_enable_autosignin": False,
        "autofill": {"profile_enabled": False, "credit_card_enabled": False},
        "search": {"suggest_enabled": False},
        "profile": {
            "exit_type": "Normal",
            "exited_cleanly": True,
            "password_manager_enabled": False,
            "default_content_setting_values": {
                "notifications": BLOCK,
                "geolocation": BLOCK,
            },
        },
    }


def deep_merge(base: dict, overlay: dict) -> dict:
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _load_json(path: Path) -> Optional[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def preferences_path(profile_dir: Path) -> Path:
    return Path(profile_dir) / "Default" / "Preferences"


def seed_profile(profile_dir: Path, services: bool = True) -> Path:
    """Create or update the profile's Preferences with the kiosk defaults."""
    path = preferences_path(profile_dir)
    data = _load_json(path)
    if data is None:
        atomic_write_bytes(path.with_name("Preferences.corrupt"), path.read_bytes())
        data = {}
    deep_merge(data, managed_preferences(services))
    atomic_write_json(path, data, compact=True)
    return path


def mark_clean_exit(profile_dir: Path) -> bool:
    """Flag the last session as cleanly closed so no restore prompt appears.

    Steam ends games by signalling their process tree, which Chromium can record
    as a crash. Returns ``True`` when the file had to be changed.
    """
    path = preferences_path(profile_dir)
    data = _load_json(path)
    if not data:
        return False
    profile = data.setdefault("profile", {})
    if not isinstance(profile, dict):
        return False
    if profile.get("exit_type") == "Normal" and profile.get("exited_cleanly") is True:
        return False
    profile["exit_type"] = "Normal"
    profile["exited_cleanly"] = True
    atomic_write_json(path, data, compact=True)
    return True


def profile_dir(app_home: Path, account: Optional[int], per_account: bool = True) -> Path:
    """Helium user-data directory for a Steam account, or the shared one."""
    if per_account and account:
        return Path(app_home) / ACCOUNT_PROFILES / str(account)
    return Path(app_home) / SHARED_PROFILE


def all_profiles(app_home: Path) -> List[Path]:
    shared = Path(app_home) / SHARED_PROFILE
    accounts = Path(app_home) / ACCOUNT_PROFILES
    found = [shared] if shared.is_dir() else []
    if accounts.is_dir():
        found += sorted(
            (child for child in accounts.iterdir() if child.is_dir() and child.name.isdecimal()),
            key=lambda child: int(child.name),
        )
    return found


def in_use(directory: Path) -> bool:
    """True while a running browser holds the profile's singleton lock.

    The lock names ``host-pid``; a lock left behind by a killed browser can
    point at a PID that now belongs to an unrelated process, so the process
    must also be a Chromium-family browser.
    """
    try:
        owner = os.readlink(Path(directory) / "SingletonLock")
        pid = owner.rsplit("-", 1)[-1]
        executable = os.readlink(f"/proc/{pid}/exe") if pid.isdigit() else ""
    except OSError:
        return False
    if executable.endswith(DELETED):
        executable = executable[: -len(DELETED)]
    return Path(executable).name in BROWSER_BINARIES


def adopt_shared_profile(app_home: Path, account: int) -> bool:
    """Hand the shared profile to ``account`` when profiles are first split per account.

    Earlier releases kept one profile for everybody. Moving it to the account
    that signs in first keeps that person's YouTube sign-in; other accounts
    start with their own empty profile.
    """
    shared = Path(app_home) / SHARED_PROFILE
    accounts = Path(app_home) / ACCOUNT_PROFILES
    target = accounts / str(account)
    if not adoption_pending(app_home) or target.exists() or in_use(shared):
        return False
    accounts.mkdir(parents=True, exist_ok=True)
    os.replace(shared, target)
    return True


def adoption_pending(app_home: Path) -> bool:
    """True while a shared profile from an earlier release waits for its owner."""
    accounts = Path(app_home) / ACCOUNT_PROFILES
    if not (Path(app_home) / SHARED_PROFILE).is_dir():
        return False
    return not (accounts.is_dir() and any(child.is_dir() for child in accounts.iterdir()))


def resolve_profile(app_home: Path, account: Optional[int], per_account: bool = True) -> Path:
    """Profile a launch for ``account`` should use, handing over the shared profile on first use.

    While the shared profile is still open in a browser it cannot move, so the
    launch keeps using it and the hand-over happens next time.
    """
    if not (per_account and account):
        return profile_dir(app_home, None, per_account=False)
    if adopt_shared_profile(app_home, account) or not adoption_pending(app_home):
        return profile_dir(app_home, account)
    return profile_dir(app_home, None, per_account=False)


def prepare_profile(directory: Path, services: bool = True) -> Path:
    """Seed a new profile with the kiosk defaults, or tidy an existing one before launch."""
    if preferences_path(directory).exists():
        mark_clean_exit(directory)
    else:
        seed_profile(directory, services)
    return Path(directory)
