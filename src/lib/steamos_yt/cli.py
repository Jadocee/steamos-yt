"""Command-line entry point used by the shell scripts (``steamos-yt-helper``)."""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from . import __version__, identity, profile, steam

EXIT_ERROR = 1
EXIT_NO_STEAM = 3


def _warn(message: str) -> None:
    print(f"steamos-yt: {message}", file=sys.stderr)


def _flag(value: str) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _resolve(args) -> tuple:
    root = steam.find_steam_root(args.steam_root)
    if root is None:
        raise LookupError("no Steam installation with a userdata folder was found")
    accounts = steam.select_accounts(root, args.user)
    if not accounts:
        raise LookupError(f"no Steam accounts found in {root / 'userdata'}; sign in to Steam once first")
    return root, accounts


def _report(results: List[steam.ShortcutResult], verb: str, as_json: bool) -> None:
    if as_json:
        payload = [
            {
                "account": result.account,
                "appid": result.appid,
                "game_id": result.game_id,
                "name": result.name,
                "created": result.created,
                "artwork": [str(path) for path in result.artwork],
            }
            for result in results
        ]
        print(json.dumps(payload, indent=2))
        return
    for result in results:
        action = ("added" if result.created else "updated") if verb == "add" else verb
        print(
            f"Steam account {result.account}: {action} \"{result.name}\" "
            f"(app ID {result.appid}, steam://rungameid/{result.game_id})"
        )


def cmd_steam_root(args) -> int:
    root = steam.find_steam_root(args.steam_root)
    if root is None:
        return EXIT_NO_STEAM
    print(root)
    return 0


def cmd_shortcut_add(args) -> int:
    root, accounts = _resolve(args)
    artwork = steam.collect_artwork(Path(args.artwork_dir)) if args.artwork_dir else {}
    logo = steam.LogoPosition.parse(args.logo_position) if args.logo_position else None
    spec = steam.ShortcutSpec(
        name=args.name,
        exe=args.exe,
        start_dir=args.start_dir or str(Path(args.exe).parent),
        launch_options=args.launch_options,
    )
    results = steam.add_shortcut(root, accounts, spec, artwork, logo, rename=args.rename, backup=not args.no_backup)
    _report(results, "add", args.json)
    return 0


def cmd_shortcut_remove(args) -> int:
    root, accounts = _resolve(args)
    results = steam.remove_shortcut(root, accounts, args.exe, backup=not args.no_backup)
    _report(results, "removed", args.json)
    return 0


def cmd_shortcut_status(args) -> int:
    root, accounts = _resolve(args)
    results = steam.shortcut_status(root, accounts, args.exe)
    _report(results, "present", args.json)
    return 0 if results else EXIT_ERROR


def cmd_profile_seed(args) -> int:
    path = profile.seed_profile(Path(args.profile), services=not args.no_services)
    print(path)
    return 0


def cmd_profile_clean_exit(args) -> int:
    profile.mark_clean_exit(Path(args.profile))
    return 0


def _page_settings(args) -> identity.PageSettings:
    settings = identity.PageSettings(controller=_flag(args.controller), exit_combo=_flag(args.exit_combo))
    try:
        settings.cursor_hide_seconds = max(0.0, float(args.cursor_hide))
    except ValueError:
        _warn(f"ignoring invalid cursor hide delay {args.cursor_hide!r}")
    try:
        identity.normalise_resolution(args.max_resolution)
        settings.max_resolution = args.max_resolution
    except ValueError as exc:
        _warn(f"{exc}; using auto")
    codecs = [codec for codec in re.split(r"[,\s]+", args.block_codecs or "") if codec]
    try:
        identity.normalise_codecs(codecs)
        settings.block_codecs = codecs
    except ValueError as exc:
        _warn(f"{exc}; not blocking any codecs")
    return settings


def _identity_for(args) -> tuple:
    if args.user_agent:
        return None, args.user_agent
    if args.identity == "browser":
        return None, ""
    ident = identity.cobalt_identity()
    return ident, ident.user_agent


def cmd_launch_prepare(args) -> int:
    """Refresh generated extension files and tidy the profile.

    Prints two lines: the user agent to pass to Helium (empty for its default)
    and the URL to open, which is a boot screen while the identity rules load.
    """
    ident, user_agent = _identity_for(args)
    open_url = args.url
    if args.extension:
        identity.write_extension_config(Path(args.extension), ident, _page_settings(args), args.url)
        if args.url and ident is not None:
            open_url = identity.splash_url(args.url)
    if args.profile:
        profile.mark_clean_exit(Path(args.profile))
    print(user_agent)
    print(open_url)
    return 0


def cmd_identity(args) -> int:
    ident, user_agent = _identity_for(args)
    payload = {"user_agent": user_agent, "client_hints": ident.client_hints() if ident else {}}
    if ident:
        payload["identity"] = dataclasses.asdict(ident)
    print(json.dumps(payload, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="steamos-yt-helper", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    def steam_options(sub: argparse.ArgumentParser, default_user: str) -> None:
        sub.add_argument("--steam-root", help="Steam installation directory (auto-detected by default)")
        sub.add_argument("--user", default=default_user, help="auto, all, or an account ID / SteamID64")
        sub.add_argument("--json", action="store_true", help="print machine-readable output")

    sub = commands.add_parser("steam-root", help="print the detected Steam directory")
    sub.add_argument("--steam-root")
    sub.set_defaults(func=cmd_steam_root)

    sub = commands.add_parser("shortcut-add", help="add or refresh the non-Steam shortcut")
    steam_options(sub, "auto")
    sub.add_argument("--exe", required=True)
    sub.add_argument("--name", required=True)
    sub.add_argument("--start-dir")
    sub.add_argument("--launch-options", default="")
    sub.add_argument("--artwork-dir")
    sub.add_argument("--logo-position", help="PIN[:WIDTH%%[:HEIGHT%%]], e.g. BottomLeft:45:60")
    sub.add_argument("--rename", action="store_true", help="rename an existing shortcut to --name")
    sub.add_argument("--no-backup", action="store_true")
    sub.set_defaults(func=cmd_shortcut_add)

    sub = commands.add_parser("shortcut-remove", help="remove the shortcut and its artwork")
    steam_options(sub, "all")
    sub.add_argument("--exe", required=True)
    sub.add_argument("--no-backup", action="store_true")
    sub.set_defaults(func=cmd_shortcut_remove)

    sub = commands.add_parser("shortcut-status", help="show where the shortcut is installed")
    steam_options(sub, "all")
    sub.add_argument("--exe", required=True)
    sub.set_defaults(func=cmd_shortcut_status)

    sub = commands.add_parser("profile-seed", help="write the kiosk defaults into the Helium profile")
    sub.add_argument("--profile", required=True)
    sub.add_argument("--no-services", action="store_true", help="do not opt in to Helium services")
    sub.set_defaults(func=cmd_profile_seed)

    sub = commands.add_parser("profile-clean-exit", help="suppress the 'restore pages' prompt")
    sub.add_argument("--profile", required=True)
    sub.set_defaults(func=cmd_profile_clean_exit)

    def identity_options(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--identity", choices=("cobalt", "browser"), default="cobalt")
        sub.add_argument("--user-agent", default="", help="custom user agent (disables Client Hint rewriting)")

    sub = commands.add_parser("launch-prepare", help="prepare extension config and profile before launch")
    identity_options(sub)
    sub.add_argument("--profile")
    sub.add_argument("--extension")
    sub.add_argument("--url", default="", help="page the kiosk should end up on")
    sub.add_argument("--controller", default="1")
    sub.add_argument("--cursor-hide", default="3")
    sub.add_argument("--max-resolution", default="auto")
    sub.add_argument("--block-codecs", default="")
    sub.add_argument("--exit-combo", default="1")
    sub.set_defaults(func=cmd_launch_prepare)

    sub = commands.add_parser("identity", help="print the user agent and Client Hints in use")
    identity_options(sub)
    sub.set_defaults(func=cmd_identity)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except LookupError as exc:
        print(f"steamos-yt: {exc}", file=sys.stderr)
        return EXIT_NO_STEAM
    except (steam.SteamError, OSError) as exc:
        print(f"steamos-yt: {exc}", file=sys.stderr)
        return EXIT_ERROR
