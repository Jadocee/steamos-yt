"""Install, update, remove and run apps from Flathub with the ``flatpak`` command."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

REMOTE = "flathub"
REMOTE_URL = "https://dl.flathub.org/repo/flathub.flatpakrepo"


class FlatpakError(RuntimeError):
    """A ``flatpak`` command failed."""


@dataclass(frozen=True)
class Installed:
    version: str
    installation: str


class Flatpak:
    """Thin wrapper around the ``flatpak`` command; apps NonSteamApps installs go into the user installation."""

    def __init__(self, command: str = "flatpak") -> None:
        self.command = command

    def available(self) -> bool:
        return shutil.which(self.command) is not None

    def _call(self, *args: str, quiet: bool = False) -> None:
        stream = subprocess.DEVNULL if quiet else None
        try:
            result = subprocess.run([self.command, *args], stdin=subprocess.DEVNULL, stdout=stream, check=False)
        except OSError as exc:
            raise FlatpakError(f"could not run {self.command}: {exc}") from exc
        if result.returncode != 0:
            raise FlatpakError(f"'flatpak {' '.join(args)}' failed with exit status {result.returncode}")

    def installed(self) -> Dict[str, Installed]:
        """Map installed app IDs to their version and installation, preferring the user installation."""
        try:
            output = subprocess.run(
                [self.command, "list", "--app", "--columns=application,version,installation"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        except (OSError, subprocess.CalledProcessError):
            return {}
        apps: Dict[str, Installed] = {}
        for line in output.splitlines():
            fields = [field.strip() for field in line.split("\t")]
            if len(fields) < 3:
                fields = line.split()
            if len(fields) < 2 or "." not in fields[0]:
                continue
            app_id, version, installation = fields[0], (fields[1] if len(fields) > 2 else ""), fields[-1]
            if app_id not in apps or installation == "user":
                apps[app_id] = Installed(version, installation)
        return apps

    def installation(self, app_id: str) -> Optional[str]:
        found = self.installed().get(app_id)
        return found.installation if found else None

    def install(self, app_id: str) -> None:
        self._call("remote-add", "--user", "--if-not-exists", REMOTE, REMOTE_URL)
        self._call("install", "--user", "--noninteractive", "-y", REMOTE, app_id)

    def update(self, app_ids: Sequence[str], quiet: bool = False) -> None:
        if app_ids:
            self._call("update", "--user", "--noninteractive", "-y", *app_ids, quiet=quiet)

    def uninstall(self, app_id: str) -> None:
        self._call("uninstall", "--user", "--noninteractive", "-y", app_id)

    def remove_unused(self) -> None:
        self._call("uninstall", "--user", "--unused", "--noninteractive", "-y", quiet=True)

    def run_args(self, app_id: str, args: Sequence[str] = ()) -> List[str]:
        return [self.command, "run", app_id, *args]

    def run_quietly(self, app_id: str, args: Sequence[str]) -> int:
        """Run the app to completion with ``args`` (for its own maintenance options) and return its status."""
        try:
            return subprocess.run(
                self.run_args(app_id, args),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=120,
                check=False,
            ).returncode
        except (OSError, subprocess.TimeoutExpired):
            return -1
