"""Seed and maintain the dedicated Helium profile used by the kiosk."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .fsutil import atomic_write_bytes, atomic_write_json

BLOCK = 2


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
