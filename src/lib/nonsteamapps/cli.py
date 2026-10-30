"""The ``nonsteamapps`` command. Steam starts each app through ``nonsteamapps launch <app>``."""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from . import __version__, apps, config, legacy, steam, steamclient, timer, ui
from .apps import App
from .config import Paths, Record
from .flatpak import Flatpak, FlatpakError, Installed

EXIT_ERROR = 1
EXIT_INTERRUPTED = 130
PER_ACCOUNT = "PROFILE_PER_STEAM_ACCOUNT"
RESOLUTION_HINT = "⚙ ▸ Properties ▸ Shortcut ▸ Maximum Game Resolution ▸ Native"


def _refuse_root() -> None:
    if os.getuid() == 0 and os.environ.get("NONSTEAMAPPS_ALLOW_ROOT") != "1":
        raise ui.Abort("run nonsteamapps as your normal user (for example 'deck'), not as root")


def _choose(names: Sequence[str]) -> List[App]:
    chosen: List[App] = []
    for name in names:
        try:
            app = apps.by_id(name)
        except KeyError:
            raise ui.Abort(f"unknown app {name!r}; choose from: {', '.join(apps.ids())}") from None
        if app not in chosen:
            chosen.append(app)
    return chosen


def _managed(record: Record) -> List[App]:
    return [app for app in apps.APPS if app.id in record.apps]


def _listing(chosen: Sequence[App]) -> str:
    names = [f"{app.name} ({app.client})" if app.name != app.client else app.name for app in chosen]
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def _steam_root() -> Optional[Path]:
    try:
        return steam.find_steam_root()
    except steam.SteamError:
        return None


def _is_steamos() -> bool:
    try:
        text = Path("/etc/os-release").read_text(encoding="utf-8").lower()
    except OSError:
        return False
    return any(line.startswith(("id=", "id_like=")) and "steamos" in line for line in text.splitlines())


def _account_label(account: int, names: Dict[int, str]) -> str:
    name = names.get(account)
    return f"Steam account {name} ({account})" if name else f"Steam account {account}"


def _report(result: steam.ShortcutResult, verb: str, names: Dict[int, str]) -> str:
    return f"{_account_label(result.account, names)}: {verb} \"{result.name}\" (app ID {result.appid})"


def _spec(paths: Paths, app: App) -> steam.ShortcutSpec:
    return steam.ShortcutSpec(
        name=app.name,
        exe=str(paths.app_link(app.id)),
        start_dir=str(paths.program),
        launch_options=f"--steam-account {steam.ACCOUNT_PLACEHOLDER}",
        overlay=False,
        legacy_exes=app.legacy_exes,
    )


def _link(paths: Paths, app: App) -> None:
    """Point ``apps/<id>`` at the launcher; Steam runs that link, and the launcher reads the app from its name."""
    link = paths.app_link(app.id)
    link.parent.mkdir(parents=True, exist_ok=True)
    target = os.path.relpath(paths.launcher, link.parent)
    if link.is_symlink() and os.readlink(link) == target:
        return
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(target)


def steam_add(paths: Paths, chosen: Sequence[App], user: str = "all", restart: bool = True) -> None:
    root = _steam_root()
    if root is None:
        ui.warn(f"Steam was not found; sign in to Steam once, then run: {paths.launcher} steam add")
        return
    accounts = steam.select_accounts(root, user)
    if not accounts:
        ui.warn(f"no Steam account was found; sign in to Steam once, then run: {paths.launcher} steam add")
        return
    ui.log(f"Adding {_listing(chosen)} to your Steam library")
    names = steam.account_names(root)
    with steamclient.closed(f"{paths.launcher} steam add", restart):
        for app in chosen:
            artwork = steam.collect_artwork(paths.artwork(app.id))
            logo = steam.LogoPosition.parse(app.logo_position)
            for result in steam.add_shortcut(root, accounts, _spec(paths, app), artwork, logo, rename=False):
                ui.ok(_report(result, "added" if result.created else "updated", names))


def steam_remove(paths: Paths, chosen: Sequence[App], user: str = "all", restart: bool = True) -> None:
    root = _steam_root()
    if root is None:
        return
    accounts = steam.select_accounts(root, user)
    present = [app for app in chosen if steam.shortcut_status(root, accounts, str(paths.app_link(app.id)))]
    if not present:
        return
    names = steam.account_names(root)
    with steamclient.closed(f"{paths.launcher} steam remove", restart):
        for app in present:
            for result in steam.remove_shortcut(root, accounts, str(paths.app_link(app.id))):
                ui.ok(_report(result, "removed", names))


def _install_app(paths: Paths, flatpak: Flatpak, record: Record, app: App, found: Optional[Installed]) -> None:
    if found:
        version = f" {found.version}" if found.version else ""
        ui.ok(f"{app.client}{version} is already installed ({found.installation} installation)")
        record.add(app.id, installed_flatpak=False)
    else:
        ui.log(f"Installing {app.client} from Flathub ({app.flatpak})")
        flatpak.install(app.flatpak)
        record.add(app.id, installed_flatpak=True)
        ui.ok(f"Installed {app.client}")
    _link(paths, app)


def _purge(paths: Paths, app: App) -> None:
    folders = app.profile.existing(app.home(paths.home)) if app.profile else []
    for folder in folders:
        shutil.rmtree(folder)
    if folders:
        ui.ok(f"Deleted {app.name}'s data for each Steam account ({len(folders)} folder{'s' if len(folders) > 1 else ''})")


def _uninstall_flatpaks(flatpak: Flatpak, record: Record, chosen: Sequence[App]) -> None:
    installed = flatpak.installed() if flatpak.available() else {}
    removed = False
    for app in chosen:
        found = installed.get(app.flatpak)
        if found is None:
            continue
        if record.owns_flatpak(app.id) and found.installation == "user":
            ui.log(f"Uninstalling {app.client}")
            flatpak.uninstall(app.flatpak)
            removed = True
        else:
            ui.info(f"{app.client} stays installed: it was installed before NonSteamApps")
    if removed:
        flatpak.remove_unused()


def _summary(paths: Paths, managed: Sequence[App], separate: bool) -> None:
    ui.log("Done")
    width = max([len("Sign-ins:")] + [len(app.name) + 1 for app in managed]) + 1
    for app in managed:
        client = f" ({app.client})" if app.client != app.name else ""
        ui.info(f"{app.name + ':':<{width}}Steam ▸ Library ▸ Non-Steam ▸ {app.name}{client}")
    ui.info(f"{'Sign-ins:':<{width}}{'separate for each Steam account' if separate else 'shared by all Steam accounts'}")
    ui.info(f"{'TV:':<{width}}for an app's full resolution, open it in Game Mode: {RESOLUTION_HINT}")
    ui.info(f"{'Settings:':<{width}}{paths.settings}")


def cmd_install(args, paths: Paths, flatpak: Flatpak) -> int:
    _refuse_root()
    if not flatpak.available():
        raise ui.Abort("flatpak is not installed; NonSteamApps installs every app from Flathub")
    if not _is_steamos():
        ui.warn("this does not look like SteamOS; continuing anyway")
    record = Record.load(paths.record)
    old = legacy.Legacy.detect()
    chosen = _choose(args.apps) or _managed(record)
    if not chosen:
        chosen = list(apps.APPS)
        if not ui.confirm(f"Install {_listing(chosen)}?", default=True):
            raise ui.Abort(f"nothing installed; pick apps with: {paths.launcher} install {' '.join(apps.ids())}")
    youtube = apps.by_id("youtube")
    if old.present() and youtube not in chosen:
        chosen.insert(0, youtube)
        ui.info("SteamOS YT is installed, so its YouTube shortcut moves to VacuumTube")

    ui.log(f"Installing NonSteamApps {__version__} into {paths.program}")
    paths.state.mkdir(parents=True, exist_ok=True)
    fresh = not paths.settings.exists()
    message = config.install_defaults(paths.program / "share" / "config" / config.SETTINGS_FILE, paths.settings)
    if message:
        ui.info(message)
    if fresh and old.separate_profiles() is False:
        config.set_setting(paths.settings, PER_ACCOUNT, "0")
        ui.info("Kept SteamOS YT's choice of one sign-in shared by all Steam accounts")

    installed = flatpak.installed()
    for app in chosen:
        _install_app(paths, flatpak, record, app, installed.get(app.flatpak))
        record.save()

    if args.auto_update:
        timer.install(paths)
    else:
        timer.remove(paths)
    managed = _managed(record)
    if args.steam:
        steam_add(paths, managed, args.steam_user, args.restart_steam)
        if old.present():
            if ui.confirm("Remove SteamOS YT, including its Helium browser and its YouTube sign-ins?", default=True):
                for path in old.remove():
                    ui.ok(f"Removed {path}")
            else:
                ui.info(f"Kept SteamOS YT's files; Steam now starts VacuumTube for YouTube. Remove them later with: {paths.launcher} install")
    elif old.present():
        ui.info("Kept SteamOS YT, because its Steam shortcut was not moved to VacuumTube (--no-steam)")
    separate = config.enabled(config.read_settings(paths.settings).get(PER_ACCOUNT), default=True)
    _summary(paths, managed, separate)
    return 0


def cmd_remove(args, paths: Paths, flatpak: Flatpak) -> int:
    _refuse_root()
    chosen = _choose(args.apps)
    record = Record.load(paths.record)
    question = f"Remove {_listing(chosen)} from Steam"
    question += f" and delete {'its' if len(chosen) == 1 else 'their'} data for every Steam account?" if args.purge else "? Sign-ins are kept."
    if not ui.confirm(question, default=not args.purge):
        raise ui.Abort("cancelled")
    steam_remove(paths, chosen, "all", args.restart_steam)
    for app in chosen:
        paths.app_link(app.id).unlink(missing_ok=True)
        if args.purge:
            _purge(paths, app)
    if not args.keep_app:
        _uninstall_flatpaks(flatpak, record, chosen)
    for app in chosen:
        record.discard(app.id)
    record.save()
    ui.ok(f"Removed {_listing(chosen)}")
    return 0


def _parse_launch(argv: Sequence[str]) -> Tuple[str, str, bool, List[str]]:
    if not argv or argv[0].startswith("-"):
        raise ui.Abort(f"launch needs an app: {', '.join(apps.ids())}")
    app_id, rest = argv[0], list(argv[1:])
    account, verbose, extra = "", False, []
    while rest:
        argument = rest.pop(0)
        if argument == "--":
            extra += rest
            break
        if argument == "--verbose":
            verbose = True
        elif argument == "--steam-account":
            account = rest.pop(0) if rest else ""
        elif argument.startswith("--steam-account="):
            account = argument.split("=", 1)[1]
        else:
            extra.append(argument)
    return app_id, account, verbose, extra


def _redirect(log: Path) -> None:
    previous = log.with_name(log.name + ".1")
    if log.exists():
        os.replace(log, previous)
    sys.stdout.flush()
    sys.stderr.flush()
    descriptor = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    os.dup2(descriptor, 1)
    os.dup2(descriptor, 2)
    os.close(descriptor)


def cmd_launch(argv: Sequence[str], paths: Paths, flatpak: Flatpak) -> int:
    app_id, hint, verbose, extra = _parse_launch(argv)
    app = _choose([app_id])[0]
    account = None
    if config.enabled(config.read_settings(paths.settings).get(PER_ACCOUNT), default=True):
        account = steam.launch_account(_steam_root(), hint)
    paths.state.mkdir(parents=True, exist_ok=True)
    if not verbose:
        _redirect(paths.log(app.id))
    print(f"nonsteamapps {__version__}: starting {app.client} for {f'Steam account {account}' if account else 'all accounts'}")
    if account and app.profile:
        ready = app.profile.prepare(app.home(paths.home), account, lambda options: flatpak.run_quietly(app.flatpak, options))
        if not ready:
            print(f"warning: could not create {app.client}'s data for Steam account {account}; using its shared data")
            account = None
    if not account and app.profile:
        app.profile.prepare_shared(app.home(paths.home))
    command = flatpak.run_args(app.flatpak, [*app.arguments(paths.home, account), *extra])
    print("  " + " ".join(command), flush=True)
    os.execvp(command[0], command)
    return EXIT_ERROR


def cmd_update(args, paths: Paths, flatpak: Flatpak) -> int:
    record = Record.load(paths.record)
    installed = flatpak.installed()
    ours = [
        app for app in _managed(record)
        if record.owns_flatpak(app.id) and getattr(installed.get(app.flatpak), "installation", "") == "user"
    ]
    if not ours:
        ui.info("NonSteamApps installed no apps to update; Discover updates the rest")
        return 0
    ui.log(f"Updating {_listing(ours)}")
    flatpak.update([app.flatpak for app in ours], quiet=ui.quiet)
    ui.ok("Apps are up to date")
    return 0


def cmd_steam(args, paths: Paths, flatpak: Flatpak) -> int:
    _refuse_root()
    chosen = _choose(args.apps) or _managed(Record.load(paths.record))
    if not chosen:
        raise ui.Abort(f"no apps are installed; install some with: {paths.launcher} install")
    if args.action == "add":
        steam_add(paths, chosen, args.user or "all", args.restart_steam)
    elif args.action == "remove":
        steam_remove(paths, chosen, args.user or "all", args.restart_steam)
    else:
        root = _steam_root()
        if root is None:
            raise ui.Abort("Steam was not found")
        accounts = steam.select_accounts(root, args.user or "all")
        names = steam.account_names(root)
        for app in chosen:
            results = steam.shortcut_status(root, accounts, str(paths.app_link(app.id)))
            for result in results:
                print(_report(result, "present", names))
            if not results:
                print(f"{app.name}: not in the Steam library (add it with: {paths.launcher} steam add {app.id})")
    return 0


def _describe(app: App, record: Record, found: Optional[Installed]) -> str:
    if found is None:
        return "not installed"
    version = f" {found.version}" if found.version else ""
    origin = ", installed by NonSteamApps" if record.owns_flatpak(app.id) else ""
    return f"{app.client}{version} ({found.installation} installation{origin})"


def cmd_list(args, paths: Paths, flatpak: Flatpak) -> int:
    record = Record.load(paths.record)
    installed = flatpak.installed() if flatpak.available() else {}
    for app in apps.APPS:
        status = _describe(app, record, installed.get(app.flatpak))
        managed = "in use" if app.id in record.apps else "available"
        print(f"{app.id:<10}{managed:<11}{status}")
        print(f"{'':<21}{app.summary}")
    return 0


def _size(path: Path) -> str:
    total = sum(entry.stat().st_size for entry in path.rglob("*") if entry.is_file() and not entry.is_symlink())
    for unit in ("B", "KB", "MB", "GB"):
        if total < 1024 or unit == "GB":
            return f"{total:.0f} {unit}" if unit == "B" else f"{total:.1f} {unit}"
        total /= 1024
    return ""


def cmd_doctor(args, paths: Paths, flatpak: Flatpak) -> int:
    try:
        release = dict(
            line.split("=", 1) for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines() if "=" in line
        ).get("PRETTY_NAME", "unknown").strip('"')
    except OSError:
        release = "unknown"
    settings = config.read_settings(paths.settings)
    separate = config.enabled(settings.get(PER_ACCOUNT), default=True)
    print(ui.bold(f"NonSteamApps {__version__}"))
    rows = [
        ("System", f"{release} ({platform.machine()}, kernel {platform.release()})"),
        ("Session", "Game Mode (gamescope)" if steamclient.in_game_mode() else f"{os.environ.get('XDG_SESSION_TYPE', 'unknown')} desktop"),
        ("Program", str(paths.program)),
        ("Settings", f"{paths.settings} (sign-ins {'separate for each Steam account' if separate else 'shared'})"),
        ("Python", platform.python_version()),
        ("Flatpak", "available" if flatpak.available() else "not installed"),
        ("Updates", timer.status(paths)),
    ]
    root = _steam_root()
    rows.append(("Steam", f"{root} ({'running' if steamclient.running() else 'not running'})" if root else "not found"))
    for label, value in rows:
        print(f"  {label:<10} {value}")
    record = Record.load(paths.record)
    installed = flatpak.installed() if flatpak.available() else {}
    accounts = steam.account_ids(root) if root else []
    names = steam.account_names(root) if root else {}
    print(ui.bold("Apps"))
    for app in apps.APPS:
        if app.id not in record.apps and app.flatpak not in installed:
            continue
        print(f"  {app.id:<10} {_describe(app, record, installed.get(app.flatpak))}")
        if root:
            for result in steam.shortcut_status(root, accounts, str(paths.app_link(app.id))):
                print(f"  {'':<10} {_report(result, 'in the library as', names)}")
        for folder in app.profile.existing(app.home(paths.home)) if app.profile else []:
            print(f"  {'':<10} data: {folder} ({_size(folder)})")
        log = paths.log(app.id)
        if log.is_file():
            lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
            print(f"  {'':<10} last launch log ({log}):")
            for line in lines[-8:]:
                print(f"  {'':<12} {line}")
    return 0


def cmd_uninstall(args, paths: Paths, flatpak: Flatpak) -> int:
    _refuse_root()
    if not (paths.program / "lib" / config.NAME / "__init__.py").is_file():
        raise ui.Abort(f"refusing to remove unexpected directory {paths.program}")
    record = Record.load(paths.record)
    managed = _managed(record)
    question = "Remove NonSteamApps and its Steam shortcuts"
    if managed and not args.keep_apps:
        question += f", and uninstall {_listing(managed)}"
    question += ", deleting every app's sign-ins and your settings?" if args.purge else "? Sign-ins and settings are kept."
    if not ui.confirm(question, default=not args.purge):
        raise ui.Abort("cancelled")
    ui.log("Removing NonSteamApps")
    steam_remove(paths, managed, "all", args.restart_steam)
    if args.purge:
        for app in managed:
            _purge(paths, app)
    if not args.keep_apps:
        _uninstall_flatpaks(flatpak, record, managed)
    timer.remove(paths)
    shutil.rmtree(paths.state, ignore_errors=True)
    if args.purge:
        shutil.rmtree(paths.config, ignore_errors=True)
    shutil.rmtree(paths.program)
    ui.ok("Removed NonSteamApps" + ("" if args.purge else f"; sign-ins stay in ~/.var/app and settings in {paths.config}"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=config.NAME,
        description="Install apps from Flathub and add them to the Steam library, with separate sign-ins per Steam account.",
        epilog=f"Apps: {', '.join(apps.ids())}. Steam starts each one with: {config.NAME} launch APP [--steam-account ID] [-- ARGS]",
    )
    parser.add_argument("--version", action="version", version=f"{config.NAME} {__version__}")
    commands = parser.add_subparsers(dest="command", metavar="command")
    commands.required = True

    def common(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("-y", "--yes", action="store_true", help="answer yes to every question")
        sub.add_argument("-q", "--quiet", action="store_true", help="only print warnings and errors")

    def restart(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--no-restart-steam", dest="restart_steam", action="store_false",
                         help="leave Steam closed after changing its library")

    sub = commands.add_parser("install", help="install or repair apps and add them to Steam (default: the apps in use, else all)")
    sub.add_argument("apps", nargs="*", metavar="APP")
    sub.add_argument("--steam-user", default="all", help="Steam accounts that get shortcuts: all (default), auto or an account ID")
    sub.add_argument("--no-steam", dest="steam", action="store_false", help="do not change the Steam library")
    sub.add_argument("--no-auto-update", dest="auto_update", action="store_false", help="do not install the weekly update timer")
    restart(sub)
    common(sub)
    sub.set_defaults(func=cmd_install)

    sub = commands.add_parser("remove", help="remove apps from Steam and uninstall the ones NonSteamApps installed")
    sub.add_argument("apps", nargs="+", metavar="APP")
    sub.add_argument("--purge", action="store_true", help="also delete the apps' data for every Steam account")
    sub.add_argument("--keep-app", action="store_true", help="only remove the Steam shortcut; keep the app installed")
    restart(sub)
    common(sub)
    sub.set_defaults(func=cmd_remove)

    sub = commands.add_parser("list", help="show every app and whether it is installed")
    sub.set_defaults(func=cmd_list)

    sub = commands.add_parser("update", help="update the apps NonSteamApps installed")
    common(sub)
    sub.set_defaults(func=cmd_update)

    sub = commands.add_parser("steam", help="add, remove or show Steam shortcuts (default: every app in use)")
    sub.add_argument("action", choices=("add", "remove", "status"))
    sub.add_argument("apps", nargs="*", metavar="APP")
    sub.add_argument("--user", help="all (default), auto (the most recent sign-in) or an account ID")
    restart(sub)
    common(sub)
    sub.set_defaults(func=cmd_steam)

    sub = commands.add_parser("doctor", help="show diagnostics for troubleshooting")
    sub.set_defaults(func=cmd_doctor)

    sub = commands.add_parser("uninstall", help="remove NonSteamApps, its shortcuts and the apps it installed")
    sub.add_argument("--purge", action="store_true", help="also delete every app's data and your settings")
    sub.add_argument("--keep-apps", action="store_true", help="keep the apps installed")
    restart(sub)
    common(sub)
    sub.set_defaults(func=cmd_uninstall)

    sub = commands.add_parser("launch", help="start an app (what Steam runs)")
    sub.add_argument("app", metavar="APP")
    return parser


def main(argv: Optional[Sequence[str]] = None, paths: Optional[Paths] = None, flatpak: Optional[Flatpak] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    paths = paths or Paths.detect()
    flatpak = flatpak or Flatpak()
    try:
        if argv and argv[0] == "launch":
            return cmd_launch(argv[1:], paths, flatpak)
        args = build_parser().parse_args(argv)
        ui.quiet = getattr(args, "quiet", False)
        ui.assume_yes = getattr(args, "yes", False)
        return args.func(args, paths, flatpak)
    except ui.Abort as exc:
        ui.error(str(exc))
    except (steam.SteamError, FlatpakError, OSError) as exc:
        ui.error(str(exc))
    except KeyboardInterrupt:
        return EXIT_INTERRUPTED
    return EXIT_ERROR
