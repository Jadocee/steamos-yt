"""Device identity and page settings handed to YouTube's TV client.

YouTube only serves its TV interface (Leanback) to user agents that belong to a
TV or console client, and tunes the UI and player to that identity. The default
identity follows the format Cobalt, YouTube's TV runtime, generates for its
desktop Linux build. Matching User-Agent Client Hints keep request headers and
``navigator.userAgentData`` consistent with the user agent.
"""

from __future__ import annotations

import datetime
import json
import platform
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote

from . import __version__
from .fsutil import atomic_write_bytes, atomic_write_json

COBALT_VERSION = "27.lts.3.1040976-gold"
V8_VERSION = "13.8.258.54"
STARBOARD_API = 18
BRAND = "SteamOSYT"
APP_ID = "io.github.jadocee.SteamOSYT"

TV_DOCUMENT_REGEX = r"^https://www\.youtube\.com/tv(?:[/?#]|$)"
GOOGLE_DOMAINS = [
    "youtube.com",
    "youtube-nocookie.com",
    "googlevideo.com",
    "ytimg.com",
    "ggpht.com",
    "google.com",
    "googleapis.com",
    "gstatic.com",
    "googleusercontent.com",
    "doubleclick.net",
]
RESOURCE_TYPES = [
    "main_frame",
    "sub_frame",
    "stylesheet",
    "script",
    "image",
    "font",
    "object",
    "xmlhttprequest",
    "ping",
    "csp_report",
    "media",
    "websocket",
    "webtransport",
    "webbundle",
    "other",
]
RESOLUTIONS = {
    "720p": "1280x720",
    "1080p": "1920x1080",
    "1440p": "2560x1440",
    "2160p": "3840x2160",
    "4k": "3840x2160",
    "4320p": "7680x4320",
    "8k": "7680x4320",
}
CODECS = ("av1", "vp9", "vp8", "h264")
SPONSORBLOCK_CATEGORIES = (
    "sponsor",
    "selfpromo",
    "interaction",
    "intro",
    "outro",
    "preview",
    "hook",
    "filler",
    "music_offtopic",
)
DEFAULT_SPONSORBLOCK_CATEGORIES = ("sponsor", "selfpromo", "interaction")

_ARCHITECTURES = {
    "x86_64": ("x86_64", "x8664", "x86", "64"),
    "amd64": ("x86_64", "x8664", "x86", "64"),
    "aarch64": ("aarch64", "arm64", "arm", "64"),
    "arm64": ("aarch64", "arm64", "arm", "64"),
}


@dataclass(frozen=True)
class Identity:
    user_agent: str
    brand: str
    major_version: str
    full_version: str
    platform: str
    architecture: str
    bitness: str

    def client_hints(self) -> Dict[str, str]:
        return {
            "sec-ch-ua": f'"{self.brand}";v="{self.major_version}"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": f'"{self.platform}"',
            "sec-ch-ua-full-version-list": f'"{self.brand}";v="{self.full_version}"',
            "sec-ch-ua-full-version": f'"{self.full_version}"',
            "sec-ch-ua-platform-version": '""',
            "sec-ch-ua-arch": f'"{self.architecture}"',
            "sec-ch-ua-bitness": f'"{self.bitness}"',
            "sec-ch-ua-model": '""',
            "sec-ch-ua-wow64": "?0",
        }

    def to_page(self) -> dict:
        return {
            "brand": self.brand,
            "majorVersion": self.major_version,
            "fullVersion": self.full_version,
            "platform": self.platform,
            "architecture": self.architecture,
            "bitness": self.bitness,
        }


@dataclass
class PageSettings:
    controller: bool = True
    cursor_hide_seconds: float = 3.0
    max_resolution: str = "auto"
    block_codecs: List[str] = field(default_factory=list)
    exit_combo: bool = True
    sponsorblock: bool = True
    sponsorblock_categories: List[str] = field(default_factory=lambda: list(DEFAULT_SPONSORBLOCK_CATEGORIES))
    dearrow: bool = True
    dearrow_thumbnails: bool = True
    return_dislikes: bool = True


def cobalt_identity(
    app_version: str = __version__,
    machine: Optional[str] = None,
    year: Optional[int] = None,
) -> Identity:
    """Build the Cobalt-style identity for this machine's CPU architecture."""
    machine = (machine or platform.machine() or "x86_64").lower()
    os_arch, chipset, architecture, bitness = _ARCHITECTURES.get(
        machine, (machine, re.sub(r"[^a-z0-9]", "", machine) or "unknown", "x86", "64")
    )
    year = year or datetime.date.today().year
    user_agent = (
        f"Mozilla/5.0 (X11; Linux {os_arch}) Cobalt/{COBALT_VERSION} (unlike Gecko) "
        f"v8/{V8_VERSION}-jit gles Starboard/{STARBOARD_API}, "
        f"{BRAND}_DESKTOP_{chipset}_{year}/{app_version} ({BRAND}, Linux) {APP_ID}/{app_version}"
    )
    full_version = ".".join(COBALT_VERSION.split("-")[0].split(".")[:3])
    return Identity(user_agent, BRAND, COBALT_VERSION.split(".")[0], full_version, "Starboard", architecture, bitness)


def dnr_rules(identity: Optional[Identity], settings: Optional["PageSettings"] = None) -> List[dict]:
    """declarativeNetRequest rules for the kiosk.

    Rule 1 aligns Client Hints with ``identity``. Rule 2 drops the TV page's
    Content Security Policy, whose ``img-src`` list would otherwise block
    DeArrow thumbnails; it only exists while DeArrow thumbnails are enabled.
    """
    rules = []
    if identity is not None:
        headers = [
            {"header": name, "operation": "set", "value": value}
            for name, value in identity.client_hints().items()
        ]
        rules.append(
            {
                "id": 1,
                "priority": 1,
                "action": {"type": "modifyHeaders", "requestHeaders": headers},
                "condition": {"requestDomains": GOOGLE_DOMAINS, "resourceTypes": RESOURCE_TYPES},
            }
        )
    if settings is not None and settings.dearrow and settings.dearrow_thumbnails:
        rules.append(
            {
                "id": 2,
                "priority": 1,
                "action": {
                    "type": "modifyHeaders",
                    "responseHeaders": [
                        {"header": "content-security-policy", "operation": "remove"},
                        {"header": "content-security-policy-report-only", "operation": "remove"},
                    ],
                },
                "condition": {"regexFilter": TV_DOCUMENT_REGEX, "resourceTypes": RESOURCE_TYPES},
            }
        )
    return rules


def normalise_resolution(value: Optional[str]) -> str:
    value = (value or "auto").strip().lower()
    if value in ("auto", "screen"):
        return value
    if value in RESOLUTIONS:
        return RESOLUTIONS[value]
    if re.fullmatch(r"[1-9]\d{2,4}x[1-9]\d{2,4}", value):
        return value
    raise ValueError(f"unsupported resolution {value!r}; use auto, screen, 720p, 1080p, 1440p, 2160p or WIDTHxHEIGHT")


def normalise_sponsorblock_categories(values: List[str]) -> List[str]:
    categories = list(dict.fromkeys(value.strip().lower() for value in values if value.strip()))
    unknown = [category for category in categories if category not in SPONSORBLOCK_CATEGORIES]
    if unknown:
        raise ValueError(
            f"unknown SponsorBlock categor{'y' if len(unknown) == 1 else 'ies'} {', '.join(unknown)}; "
            f"choose from {', '.join(SPONSORBLOCK_CATEGORIES)}"
        )
    return categories


def normalise_codecs(values: List[str]) -> List[str]:
    codecs = sorted({value.strip().lower() for value in values if value.strip()})
    unknown = [codec for codec in codecs if codec not in CODECS]
    if unknown:
        raise ValueError(f"unknown codec(s) {', '.join(unknown)}; choose from {', '.join(CODECS)}")
    return codecs


SPLASH_MARKER = "steamos-yt-splash"
SPLASH_FALLBACK_MS = 6000
_SPLASH = (
    '<!doctype html><html lang="en"><head><meta charset="utf-8">'
    f'<meta name="{SPLASH_MARKER}" content="1"><title>YouTube</title><style>'
    "html,body{margin:0;height:100%;overflow:hidden;background:#0f0f0f;cursor:none}"
    "body{display:grid;place-items:center}"
    "svg{width:min(20vw,28vh);opacity:0;animation:in .28s ease-out .08s forwards,pulse 1.6s ease-in-out .6s infinite}"
    "@keyframes in{to{opacity:1}}@keyframes pulse{50%{transform:scale(1.04)}}"
    "</style></head><body>"
    '<svg viewBox="0 0 240 204" role="img" aria-label="Starting YouTube"><defs>'
    '<linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FF3D5E"/>'
    '<stop offset="1" stop-color="#E0001E"/></linearGradient></defs>'
    '<rect width="240" height="168" rx="46" fill="url(#g)"/>'
    '<path d="M100 58L100 110L146 84Z" fill="#fff" stroke="#fff" stroke-width="14" stroke-linejoin="round"/>'
    '<rect x="76" y="182" width="88" height="16" rx="8" fill="#FF3D5E"/></svg>'
    "<script>setTimeout(function(){location.replace(@TARGET@)},@DELAY@)</script></body></html>"
)


def page_config(identity: Optional[Identity], settings: PageSettings, target_url: str = "") -> dict:
    return {
        "version": __version__,
        "targetUrl": target_url,
        "splashMarker": SPLASH_MARKER,
        "controller": bool(settings.controller),
        "cursorHideMs": max(0, int(settings.cursor_hide_seconds * 1000)),
        "maxResolution": normalise_resolution(settings.max_resolution),
        "blockCodecs": normalise_codecs(settings.block_codecs),
        "exitCombo": bool(settings.exit_combo),
        "sponsorBlock": bool(settings.sponsorblock),
        "sponsorBlockCategories": normalise_sponsorblock_categories(settings.sponsorblock_categories),
        "deArrow": bool(settings.dearrow),
        "deArrowThumbnails": bool(settings.dearrow and settings.dearrow_thumbnails),
        "returnDislikes": bool(settings.return_dislikes),
        "headerRules": bool(dnr_rules(identity, settings)),
        "identity": identity.to_page() if identity else None,
    }


def splash_url(target: str) -> str:
    """A self-contained boot screen for the kiosk's first page.

    Helium may start its first navigation before the companion extension and
    its header rules are active. The kiosk therefore opens this page; the
    extension moves it to ``target`` once the rules are live, and the page
    redirects by itself after a few seconds should the extension be missing.
    """
    script_target = json.dumps(target).replace("<", "\\u003c")
    page = _SPLASH.replace("@DELAY@", str(SPLASH_FALLBACK_MS)).replace("@TARGET@", script_target)
    return "data:text/html;charset=utf-8," + quote(page, safe="")


def write_extension_config(
    extension_dir: Path,
    identity: Optional[Identity],
    settings: PageSettings,
    target_url: str = "",
) -> None:
    """Write the generated ``config.js`` and ``rules.json`` the companion extension loads."""
    extension_dir = Path(extension_dir)
    config = json.dumps(page_config(identity, settings, target_url), indent=2)
    script = f"globalThis.__STEAMOS_YT_CONFIG__ = Object.freeze({config});\n"
    atomic_write_bytes(extension_dir / "config.js", script.encode("utf-8"))
    atomic_write_json(extension_dir / "rules.json", dnr_rules(identity, settings))
