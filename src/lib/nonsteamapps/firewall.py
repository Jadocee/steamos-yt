"""Let other devices reach an app through firewalld, the firewall SteamOS ships.

Checking needs no privileges. Opening or closing a port runs ``firewall-cmd`` through ``sudo``,
which asks for the user's password on the terminal. Each change is made in every zone in use,
both for now and permanently.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Dict, List, Sequence

Ports = Dict[str, List[str]]


class FirewallError(Exception):
    """A firewall change failed; ``commands`` are the ones still to run by hand."""

    def __init__(self, reason: str, commands: Sequence[str]) -> None:
        super().__init__(reason)
        self.commands = list(commands)


class Firewall:
    def __init__(self, command: str = "firewall-cmd", sudo: str = "sudo") -> None:
        self.command = command
        self.sudo = sudo

    def _query(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [self.command, *args], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30, check=False
        )

    def running(self) -> bool:
        if not shutil.which(self.command):
            return False
        try:
            result = self._query("--state")
        except (OSError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0 and result.stdout.strip() == "running"

    def zones(self) -> List[str]:
        """The zones in use, or the default zone when none has an interface."""
        output = self._query("--get-active-zones").stdout
        active = [line.split()[0] for line in output.splitlines() if line[:1].strip()]
        return active or [self._query("--get-default-zone").stdout.strip() or "public"]

    def closed(self, ports: Sequence[str]) -> Ports:
        """The ports that each zone in use does not let in yet."""
        found: Ports = {}
        for zone in self.zones():
            missing = [port for port in ports if self._query(f"--zone={zone}", f"--query-port={port}").returncode != 0]
            if missing:
                found[zone] = missing
        return found

    def commands(self, action: str, ports: Ports) -> List[List[str]]:
        """The commands that ``add`` or ``remove`` ports, permanently and for now."""
        commands = []
        for zone, zone_ports in ports.items():
            change = [f"--zone={zone}", *(f"--{action}-port={port}" for port in zone_ports)]
            commands += [[self.sudo, self.command, "--permanent", *change], [self.sudo, self.command, *change]]
        return commands

    def change(self, action: str, ports: Ports) -> None:
        """Run :meth:`commands`; when one fails, raise with it and the ones after it."""
        commands = self.commands(action, ports)
        for index, command in enumerate(commands):
            try:
                result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False)
            except OSError as error:
                failure = str(error)
            else:
                lines = result.stderr.strip().splitlines()
                failure = (lines[-1] if lines else f"exit status {result.returncode}") if result.returncode else ""
            if failure:
                raise FirewallError(failure, ["sudo firewall-cmd " + " ".join(step[2:]) for step in commands[index:]])
