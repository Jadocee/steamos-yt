"""Where NonSteamApps keeps its files, its settings file and its record of installed apps."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Optional

from .fsutil import atomic_write_json

NAME = "nonsteamapps"
SETTINGS_FILE = f"{NAME}.conf"
_KEY = re.compile(r"[A-Z][A-Z0-9_]*\Z")


def xdg_dir(environ: Mapping[str, str], variable: str, home: Path, fallback: str) -> Path:
    value = environ.get(variable, "")
    return Path(value) if os.path.isabs(value) else home / fallback


@dataclass(frozen=True)
class Paths:
    home: Path
    program: Path
    config: Path
    state: Path
    systemd: Path

    @classmethod
    def detect(cls, program: Optional[Path] = None, environ: Optional[Mapping[str, str]] = None) -> "Paths":
        environ = os.environ if environ is None else environ
        home = Path(environ.get("HOME") or Path.home())
        config_home = xdg_dir(environ, "XDG_CONFIG_HOME", home, ".config")
        return cls(
            home=home,
            program=Path(program) if program else Path(__file__).resolve().parents[2],
            config=config_home / NAME,
            state=xdg_dir(environ, "XDG_STATE_HOME", home, ".local/state") / NAME,
            systemd=config_home / "systemd" / "user",
        )

    @property
    def launcher(self) -> Path:
        return self.program / "bin" / NAME

    @property
    def settings(self) -> Path:
        return self.config / SETTINGS_FILE

    @property
    def record(self) -> Path:
        return self.state / "apps.json"

    @property
    def helium(self) -> Path:
        return self.program / "helium"

    @property
    def helium_key(self) -> Path:
        return self.program / "share" / "keys" / "helium.asc"

    @property
    def profiles(self) -> Path:
        """Helium profiles, one folder per app; kept when NonSteamApps is uninstalled without --purge."""
        return self.program / "profiles"

    def profile(self, app_id: str, account: Optional[int]) -> Path:
        return self.profiles / app_id / (str(account) if account else "shared")

    def app_link(self, app_id: str) -> Path:
        return self.program / "apps" / app_id

    def artwork(self, app_id: str) -> Path:
        return self.program / "artwork" / app_id

    def log(self, app_id: str) -> Path:
        return self.state / f"{app_id}.log"


def parse_settings(text: str) -> Dict[str, str]:
    """Read ``KEY=value`` lines, ignoring comments, blank lines and malformed keys."""
    settings: Dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not _KEY.match(key):
            continue
        try:
            words = shlex.split(value, comments=True)
        except ValueError:
            words = [value.strip()]
        settings[key] = " ".join(words)
    return settings


def read_settings(path: Path) -> Dict[str, str]:
    try:
        return parse_settings(Path(path).read_text(encoding="utf-8"))
    except OSError:
        return {}


def enabled(value: Optional[str], default: bool = False) -> bool:
    if value is None or not value.strip():
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _digest(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def install_defaults(shipped: Path, target: Path) -> str:
    """Install ``shipped`` as ``target`` without overwriting the user's edits.

    Returns a message describing anything the user should know, or ``""``.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    stamp = target.with_name(f".{target.name}.sha256")
    new = _digest(shipped)
    recorded = stamp.read_text(encoding="utf-8").strip() if stamp.is_file() else ""
    pending = target.with_name(target.name + ".default")
    message = ""
    if not target.exists():
        shutil.copyfile(shipped, target)
    else:
        current = _digest(target)
        if current == new:
            pending.unlink(missing_ok=True)
        elif current == recorded:
            shutil.copyfile(shipped, target)
            pending.unlink(missing_ok=True)
            message = f"Updated {target} to the new defaults"
        else:
            shutil.copyfile(shipped, pending)
            message = f"Kept your {target.name}; the new defaults are in {pending}"
    stamp.write_text(new + "\n", encoding="utf-8")
    return message


def set_setting(path: Path, key: str, value: str) -> None:
    """Change ``key`` in a settings file in place, appending it when absent."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    pattern = re.compile(rf"\s*{re.escape(key)}\s*=")
    for index, line in enumerate(lines):
        if pattern.match(line):
            lines[index] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


class Record:
    """Which apps NonSteamApps manages, and whether it installed each app's Flatpak."""

    def __init__(self, path: Path, apps: Optional[Dict[str, dict]] = None) -> None:
        self.path = Path(path)
        self.apps: Dict[str, dict] = apps or {}

    @classmethod
    def load(cls, path: Path) -> "Record":
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls(path)
        apps = data.get("apps") if isinstance(data, dict) else None
        if not isinstance(apps, dict):
            return cls(path)
        return cls(path, {key: value for key, value in apps.items() if isinstance(value, dict)})

    def managed(self) -> List[str]:
        return list(self.apps)

    def owns_flatpak(self, app_id: str) -> bool:
        return bool(self.apps.get(app_id, {}).get("installed_flatpak"))

    def add(self, app_id: str, installed_flatpak: bool) -> None:
        self.apps[app_id] = {"installed_flatpak": installed_flatpak or self.owns_flatpak(app_id)}

    def discard(self, app_id: str) -> None:
        self.apps.pop(app_id, None)

    def save(self) -> None:
        atomic_write_json(self.path, {"version": 1, "apps": self.apps})
