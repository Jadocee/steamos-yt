"""Give shortcuts one of Valve's controller layouts, as if chosen in Steam.

Steam keeps a non-Steam shortcut's layout per Steam account and controller type in
``steamapps/common/Steam Controller Configs/<account>/config/configset_<type>.vdf``,
under the shortcut's lower-cased name; this is the format Steam ROM Manager writes.
Valve's layouts live in ``controller_base/templates``. An entry is only written
where the user has not picked a layout, and only removed where it is still ours.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

from . import vdf
from .fsutil import atomic_write_bytes

MARKER = "nonsteamapps"
_UNSAFE = re.compile(r'[/\\?%*:|"<>.]')


def entry_name(title: str) -> str:
    """The key Steam files a shortcut's layout under."""
    return _UNSAFE.sub("", (title or "").lower())


def templates_dir(root: Path) -> Path:
    return Path(root) / "controller_base" / "templates"


def config_dir(root: Path, account: int) -> Path:
    return Path(root) / "steamapps" / "common" / "Steam Controller Configs" / str(account) / "config"


def _title(mappings: vdf.KeyValues) -> str:
    localization = mappings.get("localization")
    english = localization.get("english") if isinstance(localization, vdf.KeyValues) else None
    title = english.get("title") if isinstance(english, vdf.KeyValues) else None
    return str(title or mappings.get("title") or "")


def find_templates(root: Path, title: str) -> Dict[str, str]:
    """Map each controller type to Valve's layout file called ``title`` (in English) for it."""
    found: Dict[str, str] = {}
    directory = templates_dir(root)
    if not directory.is_dir():
        return found
    for path in sorted(directory.glob("*.vdf")):
        try:
            mappings = vdf.loads_text(path.read_text(encoding="utf-8", errors="replace")).get("controller_mappings")
        except (OSError, vdf.VdfError):
            continue
        if not isinstance(mappings, vdf.KeyValues):
            continue
        kind = str(mappings.get("controller_type") or "")
        if kind.startswith("controller_") and _title(mappings).strip().lower() == title.strip().lower():
            found.setdefault(kind, path.name)
    return found


def _load(path: Path) -> vdf.KeyValues:
    try:
        return vdf.loads_text(path.read_text(encoding="utf-8", errors="replace"))
    except FileNotFoundError:
        return vdf.KeyValues()


def _section(root: vdf.KeyValues) -> vdf.KeyValues:
    section = root.get("controller_config")
    if not isinstance(section, vdf.KeyValues):
        section = vdf.KeyValues()
        root.set("controller_config", section, vdf.MAP)
    return section


def assign(root: Path, account: int, title: str, layouts: Dict[str, str]) -> List[str]:
    """Give the shortcut ``title`` these layouts; return the controller types that got one."""
    assigned = []
    name = entry_name(title)
    for kind, template in sorted(layouts.items()):
        path = config_dir(root, account) / f"configset_{kind}.vdf"
        try:
            data = _load(path)
        except (OSError, vdf.VdfError):
            continue
        section = _section(data)
        entry = section.get(name)
        if isinstance(entry, vdf.KeyValues) and entry.get(MARKER) is None and len(entry):
            continue
        if isinstance(entry, vdf.KeyValues) and entry.get("template") == template and entry.get(MARKER) is not None:
            assigned.append(kind)
            continue
        fresh = vdf.KeyValues()
        fresh.set("template", template, vdf.STRING)
        fresh.set(MARKER, "1", vdf.STRING)
        section.set(name, fresh, vdf.MAP)
        atomic_write_bytes(path, vdf.dumps_text(data).encode("utf-8"))
        assigned.append(kind)
    return assigned


def release(root: Path, account: int, title: str) -> List[str]:
    """Remove the layouts NonSteamApps gave ``title``; return the controller types changed."""
    released = []
    directory = config_dir(root, account)
    if not directory.is_dir():
        return released
    name = entry_name(title)
    for path in sorted(directory.glob("configset_controller_*.vdf")):
        try:
            data = _load(path)
        except (OSError, vdf.VdfError):
            continue
        section = data.get("controller_config")
        entry = section.get(name) if isinstance(section, vdf.KeyValues) else None
        if isinstance(entry, vdf.KeyValues) and entry.get(MARKER) is not None:
            section.remove(name)
            atomic_write_bytes(path, vdf.dumps_text(data).encode("utf-8"))
            released.append(path.stem[len("configset_"):])
    return released
