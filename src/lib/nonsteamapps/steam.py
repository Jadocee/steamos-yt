"""Steam library integration: locate the client, manage non-Steam shortcuts and artwork."""

from __future__ import annotations

import dataclasses
import os
import re
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from . import vdf
from .fsutil import atomic_copy, atomic_write_bytes, atomic_write_json

STEAM_ID64_BASE = 76561197960265728
MAX_ACCOUNT_ID = 0xFFFFFFFF
BACKUP_SUFFIX = ".nonsteamapps.bak"

ARTWORK_SLOTS = {
    "capsule": "{appid}p",
    "wide": "{appid}",
    "hero": "{appid}_hero",
    "logo": "{appid}_logo",
    "icon": "{appid}_icon",
}
ARTWORK_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".ico")
LOGO_PINS = ("BottomLeft", "UpperLeft", "CenterCenter", "UpperCenter", "BottomCenter")
ACCOUNT_PLACEHOLDER = "{account}"
_ACCOUNT_OPTION = re.compile(r"(?:^|\s)--steam-account(?:=|\s+)\d+(?=\s|$)")


class SteamError(RuntimeError):
    """Raised for Steam-related problems that should be reported to the user."""


@dataclass
class ShortcutSpec:
    name: str
    exe: str
    start_dir: str
    launch_options: str = ""
    icon: str = ""
    overlay: bool = False
    legacy_exes: Tuple[str, ...] = ()


@dataclass
class LogoPosition:
    pin: str = "BottomLeft"
    width_pct: float = 50.0
    height_pct: float = 50.0

    @classmethod
    def parse(cls, text: str) -> "LogoPosition":
        """Parse ``PIN[:WIDTH[:HEIGHT]]``, for example ``BottomLeft:42:60``."""
        parts = text.split(":")
        pin = next((name for name in LOGO_PINS if name.lower() == parts[0].strip().lower()), None)
        if pin is None:
            raise SteamError(f"unknown logo pin {parts[0]!r}; expected one of {', '.join(LOGO_PINS)}")
        try:
            numbers = [float(part) for part in parts[1:3]]
        except ValueError as exc:
            raise SteamError(f"invalid logo size in {text!r}") from exc
        if any(not 0 < number <= 100 for number in numbers):
            raise SteamError(f"logo size percentages must be within (0, 100]: {text!r}")
        width, height = (numbers + [50.0, 50.0])[:2] if numbers else (50.0, 50.0)
        return cls(pin, width, height)

    def to_json(self) -> dict:
        return {
            "nVersion": 1,
            "logoPosition": {
                "pinnedPosition": self.pin,
                "nWidthPct": self.width_pct,
                "nHeightPct": self.height_pct,
            },
        }


@dataclass
class ShortcutResult:
    account: int
    appid: int
    name: str
    created: bool = False
    artwork: List[Path] = field(default_factory=list)

    @property
    def game_id(self) -> int:
        return game_id(self.appid)


def shortcut_appid(exe: str, name: str) -> int:
    """Return the unsigned 32-bit ID Steam derives for a non-Steam shortcut."""
    return (zlib.crc32((exe + name).encode("utf-8")) & 0xFFFFFFFF) | 0x80000000


def game_id(appid: int) -> int:
    """Return the 64-bit ID used by ``steam://rungameid/`` URLs."""
    return (to_unsigned32(appid) << 32) | 0x02000000


def to_signed32(value: int) -> int:
    value &= 0xFFFFFFFF
    return value - (1 << 32) if value >= (1 << 31) else value


def to_unsigned32(value: int) -> int:
    return value & 0xFFFFFFFF


def to_account_id(steam_id: int) -> int:
    return steam_id - STEAM_ID64_BASE if steam_id >= STEAM_ID64_BASE else steam_id


def quote(path: str) -> str:
    return path if len(path) >= 2 and path[0] == path[-1] == '"' else f'"{path}"'


def unquote(value: str) -> str:
    value = value.strip()
    return value[1:-1] if len(value) >= 2 and value[0] == value[-1] == '"' else value


def _same_path(left: str, right: str) -> bool:
    return os.path.normpath(os.path.expanduser(left)) == os.path.normpath(os.path.expanduser(right))


def steam_root_candidates(home: Optional[Path] = None) -> List[Path]:
    home = Path(home) if home else Path.home()
    return [home / ".local/share/Steam", home / ".steam/steam", home / ".steam/root"]


def find_steam_root(explicit: Optional[str] = None, home: Optional[Path] = None) -> Optional[Path]:
    """Locate the native Steam installation that owns ``userdata``."""
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_dir():
            raise SteamError(f"Steam directory not found: {path}")
        return path.resolve()
    seen = set()
    for candidate in steam_root_candidates(home):
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if (resolved / "userdata").is_dir():
            return resolved
    return None


def account_ids(root: Path) -> List[int]:
    userdata = Path(root) / "userdata"
    if not userdata.is_dir():
        return []
    return sorted(
        int(child.name)
        for child in userdata.iterdir()
        if child.is_dir() and child.name.isdecimal() and int(child.name) > 0
    )


def _login_users(root: Path) -> List[Tuple[int, vdf.KeyValues]]:
    path = Path(root) / "config" / "loginusers.vdf"
    try:
        data = vdf.loads_text(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, vdf.VdfError):
        return []
    users = data.get("users")
    if not isinstance(users, vdf.KeyValues):
        return []
    return [
        (to_account_id(int(steam_id)), info)
        for steam_id, info in users.items()
        if steam_id.isdecimal() and isinstance(info, vdf.KeyValues)
    ]


def most_recent_account(root: Path) -> Optional[int]:
    """Return the account ID of the user Steam marks as most recently signed in."""
    best, best_stamp = None, -1
    for account, info in _login_users(root):
        if str(info.get("MostRecent", "0")) == "1":
            return account
        stamp = str(info.get("Timestamp", "0"))
        if stamp.isdecimal() and int(stamp) > best_stamp:
            best, best_stamp = account, int(stamp)
    return best


def account_names(root: Path) -> Dict[int, str]:
    """Map account IDs to the display names Steam remembers for them."""
    return {
        account: str(info.get("PersonaName") or info.get("AccountName") or "")
        for account, info in _login_users(root)
    }


def launch_account(root: Optional[Path], hint: Optional[str] = None) -> Optional[int]:
    """Steam account a launch belongs to.

    Each account's shortcut passes its own ``--steam-account``; launches from
    elsewhere (Desktop Mode, a terminal) fall back to the most recent sign-in.
    """
    hint = str(hint or "").strip()
    account = to_account_id(int(hint)) if hint.isdecimal() else 0
    if 0 < account <= MAX_ACCOUNT_ID:
        return account
    if root is None:
        return None
    recent = most_recent_account(root)
    if recent:
        return recent
    accounts = account_ids(root)
    return accounts[0] if len(accounts) == 1 else None


def merge_launch_options(existing: str, managed: str) -> str:
    """Put ``managed`` options into a shortcut's launch options, keeping anything else the user added."""
    remainder = _ACCOUNT_OPTION.sub("", existing or "").strip()
    if not managed:
        return remainder
    if "%command%" in remainder:
        return remainder.replace("%command%", f"%command% {managed}", 1)
    return f"{managed} {remainder}".strip()


def select_accounts(root: Path, selector: Optional[str] = "auto") -> List[int]:
    """Resolve ``auto``, ``all`` or an account/SteamID64 into account IDs."""
    available = account_ids(root)
    selector = (selector or "auto").strip().lower()
    if selector == "all":
        return available
    if selector == "auto":
        recent = most_recent_account(root)
        return [recent] if recent in available else available
    if selector.isdecimal():
        account = to_account_id(int(selector))
        if account in available:
            return [account]
        raise SteamError(f"Steam account {selector} has no userdata directory in {root}")
    raise SteamError(f"invalid Steam user selector {selector!r}; use auto, all or an account ID")


def config_dir(root: Path, account: int) -> Path:
    return Path(root) / "userdata" / str(account) / "config"


def _new_entry(appid: int, spec: ShortcutSpec) -> vdf.KeyValues:
    entry = vdf.KeyValues()
    entry.set("appid", to_signed32(appid), vdf.INT32)
    entry.set("AppName", spec.name, vdf.STRING)
    entry.set("Exe", quote(spec.exe), vdf.STRING)
    entry.set("StartDir", quote(spec.start_dir), vdf.STRING)
    entry.set("icon", spec.icon, vdf.STRING)
    entry.set("ShortcutPath", "", vdf.STRING)
    entry.set("LaunchOptions", spec.launch_options, vdf.STRING)
    entry.set("IsHidden", 0, vdf.INT32)
    entry.set("AllowDesktopConfig", 1, vdf.INT32)
    entry.set("AllowOverlay", int(spec.overlay), vdf.INT32)
    entry.set("OpenVR", 0, vdf.INT32)
    entry.set("Devkit", 0, vdf.INT32)
    entry.set("DevkitGameID", "", vdf.STRING)
    entry.set("DevkitOverrideAppID", 0, vdf.INT32)
    entry.set("LastPlayTime", 0, vdf.INT32)
    entry.set("FlatpakAppID", "", vdf.STRING)
    entry.set("sortas", "", vdf.STRING)
    entry.set("tags", vdf.KeyValues(), vdf.MAP)
    return entry


class ShortcutsFile:
    """A user's ``shortcuts.vdf`` with helpers to add, update and remove entries."""

    def __init__(self, path: Path, root: vdf.KeyValues) -> None:
        self.path = Path(path)
        self.root = root
        if not isinstance(self.root.get("shortcuts"), vdf.KeyValues):
            self.root.set("shortcuts", vdf.KeyValues(), vdf.MAP)

    @classmethod
    def load(cls, path: Path) -> "ShortcutsFile":
        path = Path(path)
        data = path.read_bytes() if path.exists() else b""
        try:
            root = vdf.loads_binary(data) if data.strip(b"\x00\x08") else vdf.KeyValues()
        except vdf.VdfError as exc:
            raise SteamError(f"{path} is not a valid shortcuts file: {exc}") from exc
        return cls(path, root)

    @property
    def shortcuts(self) -> vdf.KeyValues:
        return self.root.get("shortcuts")

    def entries(self) -> List[vdf.KeyValues]:
        return [value for value in self.shortcuts.values() if isinstance(value, vdf.KeyValues)]

    def find(self, exe: str) -> List[vdf.KeyValues]:
        return [entry for entry in self.entries() if _same_path(unquote(str(entry.get("Exe", ""))), exe)]

    @staticmethod
    def entry_appid(entry: vdf.KeyValues) -> Optional[int]:
        value = entry.get("appid")
        return to_unsigned32(value) if isinstance(value, int) else None

    def upsert(self, spec: ShortcutSpec, rename: bool = True) -> Tuple[vdf.KeyValues, int, bool]:
        """Add or refresh the shortcut whose executable is ``spec.exe``.

        Without one, an entry for any of ``spec.legacy_exes`` is taken over instead,
        so the shortcut keeps its app ID, play time and per-game settings.
        """
        matches = self.find(spec.exe) or [entry for exe in spec.legacy_exes for entry in self.find(exe)]
        if not matches:
            appid = shortcut_appid(quote(spec.exe), spec.name)
            entry = _new_entry(appid, spec)
            self.shortcuts.set(f"new-{len(self.shortcuts)}", entry, vdf.MAP)
            self._renumber()
            return entry, appid, True
        entry = matches[0]
        for duplicate in matches[1:]:
            self._drop(duplicate)
        if rename or not entry.get("AppName"):
            entry.set("AppName", spec.name)
        entry.set("Exe", quote(spec.exe))
        entry.set("StartDir", quote(spec.start_dir))
        entry.set("LaunchOptions", merge_launch_options(str(entry.get("LaunchOptions", "")), spec.launch_options))
        entry.set("AllowOverlay", int(spec.overlay), vdf.INT32)
        if spec.icon:
            entry.set("icon", spec.icon)
        appid = self.entry_appid(entry)
        if appid is None:
            appid = shortcut_appid(quote(spec.exe), str(entry.get("AppName", spec.name)))
            entry.set("appid", to_signed32(appid), vdf.INT32)
        self._renumber()
        return entry, appid, False

    def remove(self, exe: str) -> List[int]:
        removed = []
        for entry in self.find(exe):
            appid = self.entry_appid(entry)
            if appid is not None:
                removed.append(appid)
            self._drop(entry)
        self._renumber()
        return removed

    def _drop(self, target: vdf.KeyValues) -> None:
        for key, value in list(self.shortcuts.items()):
            if value is target:
                self.shortcuts.remove(key)
                return

    def _renumber(self) -> None:
        entries = self.entries()
        self.shortcuts.clear()
        for index, entry in enumerate(entries):
            self.shortcuts.set(str(index), entry, vdf.MAP)

    def save(self, backup: bool = True) -> None:
        data = vdf.dumps_binary(self.root)
        if backup and self.path.exists():
            atomic_write_bytes(self.path.with_name(self.path.name + BACKUP_SUFFIX), self.path.read_bytes())
        atomic_write_bytes(self.path, data)


def artwork_targets(grid_dir: Path, appid: int) -> Iterable[Path]:
    appid = to_unsigned32(appid)
    for template in ARTWORK_SLOTS.values():
        stem = template.format(appid=appid)
        for extension in ARTWORK_EXTENSIONS:
            yield Path(grid_dir) / f"{stem}{extension}"
    yield Path(grid_dir) / f"{appid}.json"


def install_artwork(
    grid_dir: Path,
    appid: int,
    sources: Dict[str, Path],
    logo_position: Optional[LogoPosition] = None,
) -> Dict[str, Path]:
    """Copy artwork into Steam's grid folder using the names Steam looks up."""
    appid = to_unsigned32(appid)
    grid_dir = Path(grid_dir)
    installed: Dict[str, Path] = {}
    for slot, source in sources.items():
        if slot not in ARTWORK_SLOTS:
            raise SteamError(f"unknown artwork slot {slot!r}")
        source = Path(source)
        if not source.is_file():
            raise SteamError(f"artwork file not found: {source}")
        stem = ARTWORK_SLOTS[slot].format(appid=appid)
        suffix = source.suffix.lower() or ".png"
        for extension in ARTWORK_EXTENSIONS:
            stale = grid_dir / f"{stem}{extension}"
            if extension != suffix and stale.exists():
                stale.unlink()
        destination = grid_dir / f"{stem}{suffix}"
        atomic_copy(source, destination)
        installed[slot] = destination
    if logo_position is not None:
        destination = grid_dir / f"{appid}.json"
        atomic_write_json(destination, logo_position.to_json(), compact=True)
        installed["logo_position"] = destination
    return installed


def remove_artwork(grid_dir: Path, appid: int) -> List[Path]:
    removed = []
    for path in artwork_targets(grid_dir, appid):
        if path.is_file():
            path.unlink()
            removed.append(path)
    return removed


def collect_artwork(directory: Path) -> Dict[str, Path]:
    """Map artwork slots to files named ``capsule``, ``wide``, ``hero``, ``logo`` or ``icon``."""
    directory = Path(directory)
    found: Dict[str, Path] = {}
    for slot in ARTWORK_SLOTS:
        for extension in ARTWORK_EXTENSIONS:
            candidate = directory / f"{slot}{extension}"
            if candidate.is_file():
                found[slot] = candidate
                break
    return found


def add_shortcut(
    root: Path,
    accounts: Sequence[int],
    spec: ShortcutSpec,
    artwork: Optional[Dict[str, Path]] = None,
    logo_position: Optional[LogoPosition] = None,
    rename: bool = True,
    backup: bool = True,
) -> List[ShortcutResult]:
    """Create or refresh the shortcut and its artwork for every account in ``accounts``."""
    results = []
    for account in accounts:
        directory = config_dir(root, account)
        shortcuts = ShortcutsFile.load(directory / "shortcuts.vdf")
        options = spec.launch_options.replace(ACCOUNT_PLACEHOLDER, str(account))
        entry, appid, created = shortcuts.upsert(dataclasses.replace(spec, launch_options=options), rename=rename)
        installed = install_artwork(directory / "grid", appid, artwork or {}, logo_position)
        if "icon" in installed:
            entry.set("icon", str(installed["icon"]))
        shortcuts.save(backup=backup)
        results.append(
            ShortcutResult(account, appid, str(entry.get("AppName", spec.name)), created, list(installed.values()))
        )
    return results


def remove_shortcut(root: Path, accounts: Sequence[int], exe: str, backup: bool = True) -> List[ShortcutResult]:
    results = []
    for account in accounts:
        directory = config_dir(root, account)
        path = directory / "shortcuts.vdf"
        if not path.exists():
            continue
        shortcuts = ShortcutsFile.load(path)
        names = {shortcuts.entry_appid(entry): str(entry.get("AppName", "")) for entry in shortcuts.find(exe)}
        removed = shortcuts.remove(exe)
        if not removed and not names:
            continue
        shortcuts.save(backup=backup)
        for appid in removed:
            artwork = remove_artwork(directory / "grid", appid)
            results.append(ShortcutResult(account, appid, names.get(appid, ""), False, artwork))
    return results


def shortcut_status(root: Path, accounts: Sequence[int], exe: str) -> List[ShortcutResult]:
    results = []
    for account in accounts:
        path = config_dir(root, account) / "shortcuts.vdf"
        if not path.exists():
            continue
        for entry in ShortcutsFile.load(path).find(exe):
            appid = ShortcutsFile.entry_appid(entry)
            if appid is not None:
                results.append(ShortcutResult(account, appid, str(entry.get("AppName", ""))))
    return results
