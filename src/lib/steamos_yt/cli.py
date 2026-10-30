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


def _account_label(account: int, names: Optional[dict]) -> str:
    name = (names or {}).get(account)
    return f"Steam account {name} ({account})" if name else f"Steam account {account}"


def _report(results: List[steam.ShortcutResult], verb: str, as_json: bool, names: Optional[dict] = None) -> None:
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
            f"{_account_label(result.account, names)}: {action} \"{result.name}\" "
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
    _report(results, "add", args.json, steam.account_names(root))
    return 0


def cmd_shortcut_remove(args) -> int:
    root, accounts = _resolve(args)
    results = steam.remove_shortcut(root, accounts, args.exe, backup=not args.no_backup)
    _report(results, "removed", args.json, steam.account_names(root))
    return 0


def cmd_shortcut_status(args) -> int:
    root, accounts = _resolve(args)
    results = steam.shortcut_status(root, accounts, args.exe)
    _report(results, "present", args.json, steam.account_names(root))
    return 0 if results else EXIT_ERROR


def cmd_steam_accounts(args) -> int:
    root = steam.find_steam_root(args.steam_root)
    if root is None:
        return EXIT_NO_STEAM
    names = steam.account_names(root)
    default = steam.launch_account(root)
    for account in steam.account_ids(root):
        name = " ".join(names.get(account, "").split())
        print(f"{account}\t{name}\t{1 if account == default else 0}")
    return 0


def _steam_root_or_none(explicit: Optional[str]) -> Optional[Path]:
    try:
        return steam.find_steam_root(explicit)
    except steam.SteamError:
        return None


def cmd_profile_adopt(args) -> int:
    root = _steam_root_or_none(args.steam_root)
    account = steam.launch_account(root)
    if account and profile.adopt_shared_profile(Path(args.app_home), account):
        print(_account_label(account, steam.account_names(root) if root else None))
    return 0


def cmd_profile_seed_all(args) -> int:
    for directory in profile.all_profiles(Path(args.app_home)):
        profile.seed_profile(directory, services=not args.no_services)
        print(directory)
    return 0


def _split(value: str) -> List[str]:
    return [item for item in re.split(r"[,\s]+", value or "") if item]


def _page_settings(args) -> identity.PageSettings:
    settings = identity.PageSettings(
        controller=_flag(args.controller),
        exit_combo=_flag(args.exit_combo),
        sponsorblock=_flag(args.sponsorblock),
        dearrow=_flag(args.dearrow),
        dearrow_thumbnails=_flag(args.dearrow_thumbnails),
        return_dislikes=_flag(args.return_dislikes),
        block_ads=_flag(args.block_ads),
        block_other_sites=_flag(args.block_other_sites),
    )
    try:
        settings.cursor_hide_seconds = max(0.0, float(args.cursor_hide))
    except ValueError:
        _warn(f"ignoring invalid cursor hide delay {args.cursor_hide!r}")
    try:
        identity.normalise_resolution(args.max_resolution)
        settings.max_resolution = args.max_resolution
    except ValueError as exc:
        _warn(f"{exc}; using auto")
    codecs = _split(args.block_codecs)
    try:
        identity.normalise_codecs(codecs)
        settings.block_codecs = codecs
    except ValueError as exc:
        _warn(f"{exc}; not blocking any codecs")
    categories = _split(args.sponsorblock_categories)
    try:
        settings.sponsorblock_categories = identity.normalise_sponsorblock_categories(categories)
    except ValueError as exc:
        known = [item.lower() for item in categories if item.lower() in identity.SPONSORBLOCK_CATEGORIES]
        settings.sponsorblock_categories = list(dict.fromkeys(known))
        _warn(f"{exc}; skipping only {', '.join(settings.sponsorblock_categories) or 'nothing'}")
    sites = _split(args.allowed_sites)
    try:
        settings.allowed_sites = identity.normalise_sites(sites)
    except ValueError as exc:
        settings.allowed_sites = identity.normalise_sites(site for site in sites if _valid_site(site))
        _warn(f"{exc}; ignoring them")
    return settings


def _valid_site(value: str) -> bool:
    try:
        return bool(identity.normalise_sites([value]))
    except ValueError:
        return False


def _identity_for(args) -> tuple:
    if args.user_agent:
        return None, args.user_agent
    if args.identity == "browser":
        return None, ""
    ident = identity.cobalt_identity()
    return ident, ident.user_agent


def _launch_profile(args) -> Optional[Path]:
    if args.profile:
        return Path(args.profile)
    if not args.app_home:
        return None
    per_account = _flag(args.per_account)
    account = steam.launch_account(_steam_root_or_none(args.steam_root), args.steam_account) if per_account else None
    return profile.resolve_profile(Path(args.app_home), account, per_account)


def cmd_launch_prepare(args) -> int:
    """Refresh generated extension files and pick and tidy the profile.

    Prints three lines: the user agent to pass to Helium (empty for its
    default), the URL to open (a boot screen while the header rules load) and
    the profile directory for the Steam account being served.
    """
    ident, user_agent = _identity_for(args)
    settings = _page_settings(args)
    open_url = args.url
    if args.extension:
        identity.write_extension_config(Path(args.extension), ident, settings, args.url)
        if args.url and identity.client_hint_rules(ident):
            open_url = identity.splash_url(args.url)
    directory = _launch_profile(args)
    if directory is not None:
        profile.prepare_profile(directory, services=_flag(args.helium_services))
    print(user_agent)
    print(open_url)
    print(directory or "")
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

    sub = commands.add_parser("profile-adopt", help="hand the shared profile to the most recent Steam account")
    sub.add_argument("--app-home", required=True)
    sub.add_argument("--steam-root")
    sub.set_defaults(func=cmd_profile_adopt)

    sub = commands.add_parser("profile-seed-all", help="write the kiosk defaults into every existing profile")
    sub.add_argument("--app-home", required=True)
    sub.add_argument("--no-services", action="store_true", help="do not opt in to Helium services")
    sub.set_defaults(func=cmd_profile_seed_all)

    sub = commands.add_parser("steam-accounts", help="list Steam accounts: ID, name, used by launches without an account (1/0)")
    sub.add_argument("--steam-root")
    sub.set_defaults(func=cmd_steam_accounts)

    def identity_options(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--identity", choices=("cobalt", "browser"), default="cobalt")
        sub.add_argument("--user-agent", default="", help="custom user agent (disables Client Hint rewriting)")

    sub = commands.add_parser("launch-prepare", help="prepare extension config and profile before launch")
    identity_options(sub)
    sub.add_argument("--profile", help="explicit profile directory (skips account resolution)")
    sub.add_argument("--app-home", help="install directory holding profile/ and profiles/")
    sub.add_argument("--steam-account", default="", help="account ID passed by the account's Steam shortcut")
    sub.add_argument("--steam-root")
    sub.add_argument("--per-account", default="1", help="keep a separate profile per Steam account")
    sub.add_argument("--helium-services", default="1", help="opt new profiles in to Helium services")
    sub.add_argument("--extension")
    sub.add_argument("--url", default="", help="page the kiosk should end up on")
    sub.add_argument("--controller", default="1")
    sub.add_argument("--cursor-hide", default="3")
    sub.add_argument("--max-resolution", default="auto")
    sub.add_argument("--block-codecs", default="")
    sub.add_argument("--exit-combo", default="1")
    sub.add_argument("--sponsorblock", default="1")
    sub.add_argument("--sponsorblock-categories", default=",".join(identity.DEFAULT_SPONSORBLOCK_CATEGORIES))
    sub.add_argument("--dearrow", default="1")
    sub.add_argument("--dearrow-thumbnails", default="1")
    sub.add_argument("--return-dislikes", default="1")
    sub.add_argument("--block-ads", default="1", help="remove ads from YouTube's responses")
    sub.add_argument("--block-other-sites", default="1", help="only let YouTube and its sign-in pages open")
    sub.add_argument("--allowed-sites", default="", help="further domains the kiosk may open")
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
