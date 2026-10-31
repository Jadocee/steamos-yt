"""The apps NonSteamApps can install, and how each keeps separate data per Steam account."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Union

RunApp = Callable[[Sequence[str]], int]
_STEAM_PROFILE = re.compile(r"steam-\d+\Z")
VACUUMTUBE_DEFAULTS = {"sponsorblock": True, "dearrow": True, "dislikes": True}
ELEMENT_DEFAULTS = {"minimizeToTray": False}


@dataclass(frozen=True)
class FolderProfile:
    """Per-account data in a folder chosen with one command-line argument.

    ``defaults`` are files written into a data folder that does not have them yet,
    including the app's own ``shared`` folder used when accounts share data.
    """

    folder: str
    argument: str
    shared: str = ""
    defaults: Tuple[Tuple[str, str], ...] = ()

    def path(self, app_home: Path, account: int) -> Path:
        return Path(app_home) / self.folder.format(account=account)

    def arguments(self, app_home: Path, account: int) -> List[str]:
        return [self.argument.format(folder=self.path(app_home, account), account=account)]

    def wrap(self, app_home: Path, account: int, args: Sequence[str]) -> List[str]:
        return [*args, *self.arguments(app_home, account)]

    def run_options(self) -> List[str]:
        return []

    def _seed(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        for name, content in self.defaults:
            target = folder / name
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")

    def prepare(self, app_home: Path, account: int, run_app: RunApp) -> bool:
        self._seed(self.path(app_home, account))
        return True

    def prepare_shared(self, app_home: Path) -> None:
        if self.shared and self.defaults:
            self._seed(Path(app_home) / self.shared)

    def existing(self, app_home: Path) -> List[Path]:
        pattern = re.compile(re.escape(Path(self.folder).name).replace(r"\{account\}", r"\d+") + r"\Z")
        parent = self.path(app_home, 0).parent
        if not parent.is_dir():
            return []
        return sorted(path for path in parent.iterdir() if path.is_dir() and pattern.match(path.name))


@dataclass(frozen=True)
class ScriptProfile(FolderProfile):
    """A folder handed to the app's own launch script in an environment variable (``argument`` is ``VAR={folder}``).

    ``flatpak run --env`` cannot set the XDG directories, because Flatpak sets them afterwards, so the
    script (``command``) starts through ``env`` inside the sandbox, after any ``fixed`` assignments.
    """

    command: str = ""
    fixed: Tuple[str, ...] = ()

    def wrap(self, app_home: Path, account: int, args: Sequence[str]) -> List[str]:
        return [*self.arguments(app_home, account), *self.fixed, self.command, *args]

    def run_options(self) -> List[str]:
        return ["--command=env"]


@dataclass(frozen=True)
class JellyfinProfile:
    """Jellyfin Desktop's named profiles, which must exist before ``--profile`` can select one."""

    data: str = "data/jellyfin-desktop"
    cache: str = "cache/jellyfin-desktop"

    @staticmethod
    def name(account: int) -> str:
        return f"steam-{account}"

    def arguments(self, app_home: Path, account: int) -> List[str]:
        return [f"--profile={self.name(account)}"]

    def wrap(self, app_home: Path, account: int, args: Sequence[str]) -> List[str]:
        return [*args, *self.arguments(app_home, account)]

    def run_options(self) -> List[str]:
        return []

    def prepare_shared(self, app_home: Path) -> None:
        return None

    def profiles(self, app_home: Path) -> Dict[str, Path]:
        """Map profile names to their folders, as Jellyfin Desktop records them."""
        found: Dict[str, Path] = {}
        directory = Path(app_home) / self.data / "profiles"
        if not directory.is_dir():
            return found
        for folder in sorted(directory.iterdir()):
            try:
                name = json.loads((folder / "profile.json").read_text(encoding="utf-8")).get("name")
            except (OSError, ValueError, AttributeError):
                continue
            if isinstance(name, str):
                found.setdefault(name, folder)
        return found

    def prepare(self, app_home: Path, account: int, run_app: RunApp) -> bool:
        name = self.name(account)
        if name in self.profiles(app_home):
            return True
        run_app(["--create-profile", name])
        return name in self.profiles(app_home)

    def existing(self, app_home: Path) -> List[Path]:
        folders = []
        for name, folder in self.profiles(app_home).items():
            if _STEAM_PROFILE.match(name):
                folders.append(folder)
                cache = Path(app_home) / self.cache / "profiles" / folder.name
                if cache.is_dir():
                    folders.append(cache)
        return folders


Profile = Union[FolderProfile, ScriptProfile, JellyfinProfile]
WEB_BROWSER = "Web Browser"


@dataclass(frozen=True)
class Browser:
    """An app that runs in NonSteamApps' own Helium: the browser itself, or one site full screen (kiosk)."""

    url: str = ""
    kiosk: bool = False


@dataclass(frozen=True)
class App:
    """An app NonSteamApps installs: from Flathub (``flatpak``) or in its own Helium (``browser``).

    ``controller`` names one of Valve's controller layouts to give the shortcut. ``tv_scale`` scales an
    Electron app for a TV in Game Mode, as the Helium apps always are. ``sandbox_off_when`` names
    environment variables that make the app turn Chromium's sandbox off; the launcher hides them when
    the user chooses to keep the sandbox. ``notice`` is shown after installing.
    """

    id: str
    name: str
    client: str
    summary: str
    flatpak: str = ""
    browser: Optional[Browser] = None
    args: Tuple[str, ...] = ()
    profile: Optional[Profile] = None
    controller: str = ""
    logo_position: str = "BottomLeft:42:58"
    legacy_exes: Tuple[str, ...] = ()
    tv_scale: bool = False
    sandbox_off_when: Tuple[str, ...] = ()
    notice: str = ""

    def home(self, user_home: Path) -> Path:
        """The app's own folder, which Flatpak keeps in ``~/.var/app``."""
        return Path(user_home) / ".var" / "app" / self.flatpak

    def arguments(self, user_home: Path, account: Optional[int]) -> List[str]:
        if self.profile and account:
            return self.profile.wrap(self.home(user_home), account, self.args)
        return list(self.args)

    def run_options(self, account: Optional[int]) -> List[str]:
        """Options for ``flatpak run`` itself, before the app ID."""
        return self.profile.run_options() if self.profile and account else []


APPS: Tuple[App, ...] = (
    App(
        id="youtube",
        name="YouTube",
        client="VacuumTube",
        flatpak="rocks.shy.VacuumTube",
        summary="YouTube's TV interface with ad blocking, SponsorBlock, DeArrow and dislike counts",
        args=("--fullscreen",),
        profile=FolderProfile(
            "config/VacuumTube-steam-{account}",
            "--portable={folder}",
            shared="config/VacuumTube",
            defaults=(("config.json", json.dumps(VACUUMTUBE_DEFAULTS, indent=4) + "\n"),),
        ),
        legacy_exes=("~/.local/share/steamos-yt/bin/steamos-yt",),
        sandbox_off_when=("SteamGamepadUI",),
    ),
    App(
        id="element",
        name="Element",
        client="Element Desktop",
        flatpak="im.riot.Riot",
        summary="Secure chat on Matrix",
        args=("--password-store=basic", "--storage-mode=allow-plaintext"),
        controller=WEB_BROWSER,
        profile=FolderProfile(
            "config/Element-steam-{account}",
            "--profile=steam-{account}",
            defaults=(("electron-config.json", json.dumps(ELEMENT_DEFAULTS, indent=4) + "\n"),),
        ),
        logo_position="BottomLeft:44:56",
        tv_scale=True,
    ),
    App(
        id="signal",
        name="Signal",
        client="Signal Desktop",
        flatpak="org.signal.Signal",
        summary="Private messages and calls, linked to Signal on your phone",
        controller=WEB_BROWSER,
        profile=ScriptProfile(
            "config/Signal-steam-{account}",
            "XDG_CONFIG_HOME={folder}",
            defaults=(("Signal/config.json", "{}\n"),),
            command="signal-desktop",
            fixed=("SIGNAL_PASSWORD_STORE=basic",),
        ),
        logo_position="BottomLeft:44:56",
        tv_scale=True,
        notice="Signal keeps its database key unencrypted on disk, as Flathub's Signal does by default; see the README",
    ),
    App(
        id="jellyfin",
        name="Jellyfin",
        client="Jellyfin Desktop",
        flatpak="org.jellyfin.JellyfinDesktop",
        summary="Your Jellyfin media server's films, shows and music, in its TV layout",
        args=("--tv", "--fullscreen"),
        profile=JellyfinProfile(),
        logo_position="BottomLeft:44:56",
    ),
    App(
        id="localsend",
        name="LocalSend",
        client="LocalSend",
        flatpak="org.localsend.localsend_app",
        summary="Send files to and from nearby phones and computers over your own network",
        controller=WEB_BROWSER,
        logo_position="BottomLeft:44:56",
    ),
    App(
        id="helium",
        name="Helium",
        client="Helium",
        summary="A private, ad-blocking web browser, set up for a TV and a controller",
        browser=Browser(),
        controller=WEB_BROWSER,
        logo_position="BottomLeft:44:56",
    ),
    App(
        id="primevideo",
        name="Prime Video",
        client="Helium",
        summary="Prime Video's films and series, full screen in Helium",
        browser=Browser(url="https://www.primevideo.com/", kiosk=True),
        controller=WEB_BROWSER,
        logo_position="BottomLeft:44:56",
    ),
    App(
        id="hbomax",
        name="HBO Max",
        client="Helium",
        summary="HBO Max's series and films, full screen in Helium",
        browser=Browser(url="https://www.hbomax.com/", kiosk=True),
        controller=WEB_BROWSER,
        logo_position="BottomLeft:44:56",
    ),
    App(
        id="netflix",
        name="Netflix",
        client="Helium",
        summary="Netflix's series and films, full screen in Helium",
        browser=Browser(url="https://www.netflix.com/", kiosk=True),
        controller=WEB_BROWSER,
        logo_position="BottomLeft:44:56",
    ),
    App(
        id="disneyplus",
        name="Disney+",
        client="Helium",
        summary="Disney+'s films and series, full screen in Helium",
        browser=Browser(url="https://www.disneyplus.com/", kiosk=True),
        controller=WEB_BROWSER,
        logo_position="BottomLeft:44:56",
    ),
)


def by_id(app_id: str) -> App:
    for app in APPS:
        if app.id == app_id.strip().lower():
            return app
    raise KeyError(app_id)


def ids() -> List[str]:
    return [app.id for app in APPS]
