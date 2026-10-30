"""Test doubles: the fake flatpak command and a throwaway home with Steam and a NonSteamApps program folder."""

import json
import os
import shutil
from pathlib import Path

import _paths
from nonsteamapps import steam
from nonsteamapps.config import Paths

FAKES = Path(__file__).resolve().parent / "fakes"
ALPHA, BETA = 111, 222


class FakeFlatpak:
    def __init__(self, directory: Path, installed=None):
        self.state = directory / "flatpak.json"
        self.log = directory / "flatpak.log"
        self.state.write_text(json.dumps({"apps": installed or {}}))
        self.command = str(FAKES / "flatpak")
        self.env = {"FAKE_FLATPAK_STATE": str(self.state), "FAKE_FLATPAK_LOG": str(self.log)}

    def calls(self, command=None):
        lines = self.log.read_text().splitlines() if self.log.exists() else []
        calls = [json.loads(line) for line in lines]
        return [call for call in calls if command is None or call[0] == command]

    def apps(self):
        return json.loads(self.state.read_text())["apps"]


def make_steam(home: Path, accounts=(ALPHA, BETA)) -> Path:
    root = home / ".local/share/Steam"
    for account in accounts:
        (root / "userdata" / str(account) / "config").mkdir(parents=True)
    users = "".join(
        f'"{steam.STEAM_ID64_BASE + account}" {{ "AccountName" "u{account}" "PersonaName" "P{account}" '
        f'"MostRecent" "{1 if account == accounts[0] else 0}" }}\n'
        for account in accounts
    )
    (root / "config").mkdir(parents=True)
    (root / "config/loginusers.vdf").write_text(f'"users"\n{{\n{users}}}\n')
    return root


def make_program(directory: Path) -> Path:
    shutil.copytree(_paths.ROOT / "src" / "share", directory / "share")
    shutil.copytree(_paths.ROOT / "assets" / "artwork", directory / "artwork")
    (directory / "lib" / "nonsteamapps").mkdir(parents=True)
    (directory / "lib" / "nonsteamapps" / "__init__.py").write_text("")
    (directory / "bin").mkdir()
    (directory / "bin" / "nonsteamapps").write_text("#!/bin/sh\n")
    return directory


def make_paths(home: Path) -> Paths:
    return Paths.detect(make_program(home / ".local/share/nonsteamapps"), {"HOME": str(home)})


def make_legacy(home: Path, root: Path, shared_sign_in: bool = False):
    """A SteamOS YT installation with its shortcut in every account; returns the old shortcut's app ID."""
    program = home / ".local/share/steamos-yt"
    (program / "bin").mkdir(parents=True)
    (program / "lib").mkdir()
    (program / "profiles" / str(ALPHA)).mkdir(parents=True)
    (program / "bin" / "steamos-yt").write_text("#!/bin/sh\n")
    (program / "lib" / "common.sh").write_text("")
    settings = home / ".config/steamos-yt"
    settings.mkdir(parents=True)
    (settings / "steamos-yt.conf").write_text(f"YT_PROFILE_PER_STEAM_ACCOUNT={0 if shared_sign_in else 1}\n")
    spec = steam.ShortcutSpec(
        name="YouTube",
        exe=str(program / "bin" / "steamos-yt"),
        start_dir=str(program),
        launch_options=f"--steam-account {steam.ACCOUNT_PLACEHOLDER}",
    )
    [first, *_] = steam.add_shortcut(root, steam.account_ids(root), spec)
    return first.appid


def environment(home: Path, flatpak: FakeFlatpak, extra_path: str = "") -> dict:
    env = {key: value for key, value in os.environ.items() if not key.startswith("XDG_")}
    env.update(flatpak.env, HOME=str(home), NO_COLOR="1", NONSTEAMAPPS_ALLOW_ROOT="1")
    if extra_path:
        env["PATH"] = f"{extra_path}{os.pathsep}{env.get('PATH', '')}"
    return env
