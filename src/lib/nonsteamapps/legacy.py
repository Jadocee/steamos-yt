"""Find and remove SteamOS YT, the Helium-based YouTube kiosk NonSteamApps replaces.

Its Steam shortcut is not removed here: the ``youtube`` app takes it over (see
``App.legacy_exes``), so the shortcut keeps its app ID, play time and settings.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Mapping, Optional

from . import config

NAME = "steamos-yt"
UNIT = "steamos-yt-update"


@dataclass(frozen=True)
class Legacy:
    program: Path
    config: Path
    state: Path
    cache: Path
    desktop_file: Path
    systemd: Path

    @classmethod
    def detect(cls, environ: Optional[Mapping[str, str]] = None) -> "Legacy":
        environ = os.environ if environ is None else environ
        home = Path(environ.get("HOME") or Path.home())
        data = config.xdg_dir(environ, "XDG_DATA_HOME", home, ".local/share")
        config_home = config.xdg_dir(environ, "XDG_CONFIG_HOME", home, ".config")
        return cls(
            program=data / NAME,
            config=config_home / NAME,
            state=config.xdg_dir(environ, "XDG_STATE_HOME", home, ".local/state") / NAME,
            cache=config.xdg_dir(environ, "XDG_CACHE_HOME", home, ".cache") / NAME,
            desktop_file=data / "applications" / f"{NAME}.desktop",
            systemd=config_home / "systemd" / "user",
        )

    @property
    def units(self) -> List[Path]:
        return [self.systemd / f"{UNIT}.service", self.systemd / f"{UNIT}.timer"]

    def program_is_ours(self) -> bool:
        return (self.program / "lib" / "common.sh").is_file() or (self.program / "bin" / NAME).exists()

    def leftovers(self) -> List[Path]:
        """Everything SteamOS YT left behind that can be removed safely."""
        found = [self.program] if self.program_is_ours() else []
        found += [path for path in (self.config, self.state, self.cache) if path.is_dir()]
        found += [path for path in (self.desktop_file, *self.units) if path.is_file()]
        return found

    def present(self) -> bool:
        return bool(self.leftovers())

    def separate_profiles(self) -> Optional[bool]:
        """The old per-account sign-in setting, or ``None`` when it was never changed."""
        value = config.read_settings(self.config / f"{NAME}.conf").get("YT_PROFILE_PER_STEAM_ACCOUNT")
        return None if value is None else config.enabled(value, default=True)

    def remove(self) -> List[Path]:
        """Stop its update timer and delete its files; return what was removed."""
        removed = self.leftovers()
        if any(path in removed for path in self.units) and shutil.which("systemctl"):
            subprocess.run(
                ["systemctl", "--user", "disable", "--now", f"{UNIT}.timer"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        for path in removed:
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
        if any(path in removed for path in self.units) and shutil.which("systemctl"):
            subprocess.run(["systemctl", "--user", "daemon-reload"], stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        return removed
