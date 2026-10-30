# NonSteamApps

Living-room apps for SteamOS, installed from Flathub and added to the Steam library with original artwork. Each Steam account gets its own sign-ins. The apps work in Game Mode and Desktop Mode, and NonSteamApps keeps them up to date.

| In Steam | App | From Flathub | Good to know |
| --- | --- | --- | --- |
| **YouTube** | [VacuumTube](https://github.com/shy1132/VacuumTube) | `rocks.shy.VacuumTube` | YouTube's TV interface, with controller support, ad blocking and casting from the YouTube phone app. NonSteamApps turns on SponsorBlock, DeArrow and dislike counts. |
| **Element** | [Element Desktop](https://element.io) | `im.riot.Riot` | Matrix chat. A desktop interface: use the touchscreen, the trackpads or a keyboard. |
| **Jellyfin** | [Jellyfin Desktop](https://github.com/jellyfin/jellyfin-desktop) | `org.jellyfin.JellyfinDesktop` | Your Jellyfin server in its TV layout, with controller support. It plays more formats without the server converting them. |

## Features

- **No root, nothing lost on updates.** Apps install into your user Flatpak installation, which SteamOS updates leave alone. An app you already installed, for example through Discover, is used as it is and never uninstalled.
- **Every Steam account.** Each account on the device gets a shortcut, with artwork for the library, the capsule, the hero banner, the logo and the icon. The Steam overlay is off.
- **Separate sign-ins.** Each Steam account has its own YouTube, Element and Jellyfin data (see [Several Steam accounts](#several-steam-accounts)).
- **Updates.** A weekly timer updates the apps NonSteamApps installed.
- **Replaces SteamOS YT.** On a device with this project's earlier YouTube kiosk, its YouTube shortcut moves to VacuumTube and keeps its place in the library (see [Moving from SteamOS YT](#moving-from-steamos-yt)).

## Requirements

- SteamOS 3, or another Linux system with Steam and Flatpak
- Python 3.8 or newer, `flatpak`, and `curl` and `tar` to download the installer; all are included with SteamOS
- An internet connection. The first install of each app also downloads its Flatpak runtime, which takes a while.

## Install

In Desktop Mode, open Konsole and run:

```bash
curl -fsSL https://raw.githubusercontent.com/jadocee/steamos-yt/main/install.sh | bash
```

This installs all three apps. To choose, name them:

```bash
curl -fsSL https://raw.githubusercontent.com/jadocee/steamos-yt/main/install.sh | bash -s -- youtube jellyfin
```

From a clone, run `./install.sh [APP...]`. Run it again at any time to update NonSteamApps or repair the apps you use; without names, it handles the apps already installed. Steam must be closed while its library is changed, so the installer offers to close Steam and starts it again afterwards. It cannot do that from Game Mode.

| Option | Effect |
| --- | --- |
| `--steam-user all\|auto\|ID` | Steam accounts that get shortcuts: all (default), the most recent sign-in, or one account |
| `--no-steam` | Leave the Steam library alone |
| `--no-restart-steam` | Leave Steam closed afterwards |
| `--no-auto-update` | Do not install the weekly update timer |
| `-y`, `--yes` / `-q`, `--quiet` | Answer yes to questions / print only warnings and errors |

## Using the apps

Open them from **Library → Non-Steam** in Game Mode or in the Steam client in Desktop Mode. To quit, use the app's own exit, or press the Steam button and choose **Exit game**.

- **YouTube:** controllers work out of the box. Press `Ctrl+O`, or open YouTube's settings, for VacuumTube's settings: ad blocking, SponsorBlock categories, DeArrow, dislikes, hiding Shorts, codec filters and more. To cast from a phone, choose the device in the YouTube app on the same network.
- **Element:** Element has no controller navigation. Use the touchscreen, or pick a mouse-and-keyboard layout in its controller settings (the controller icon on its library page); **Steam + X** opens the on-screen keyboard.
- **Jellyfin:** starts in its TV layout. Add your server and sign in once for each Steam account.

### On a TV: use its full resolution

In Game Mode, Steam decides the resolution each app runs at. On an external display, its default is usually lower than the TV's own. With the Steam Deck connected to the TV, select an app in your library, then **⚙ → Properties → Shortcut → Maximum Game Resolution → Native**. The setting only appears while an external display is connected. Set it for each app, and for each Steam account. [docs/plans/steam-native-resolution.md](docs/plans/steam-native-resolution.md) describes how automating this is planned.

## Several Steam accounts

Each Steam account's shortcut starts the app with `--steam-account <ID>`. NonSteamApps then points the app at that account's own data:

| App | Data for a Steam account |
| --- | --- |
| YouTube | `~/.var/app/rocks.shy.VacuumTube/config/VacuumTube-steam-<ID>` |
| Element | `~/.var/app/im.riot.Riot/config/Element-steam-<ID>` |
| Jellyfin | A Jellyfin Desktop profile named `steam-<ID>`, created on first launch |

Started from the applications menu, VacuumTube and Element use their usual data instead, and Jellyfin uses its default profile. To give every account the same data, set `PROFILE_PER_STEAM_ACCOUNT=0` in `~/.config/nonsteamapps/nonsteamapps.conf`.

## How Element keeps your sign-in

Element normally protects its stored session secrets with the system keyring. Game Mode has no keyring, and a profile protected by KWallet in Desktop Mode cannot be opened in Game Mode. Steam therefore starts Element with `--password-store=basic --storage-mode=allow-plaintext`.

The session secrets stay in the profile folder, encrypted with a fixed key rather than a password: hidden from casual view, but not protected from software running as your user. In exchange, the same profile works in both modes and Element never stops at a prompt a controller cannot answer.

To limit the risk:

- set up Element's **Secure Backup** with a recovery key;
- if the device is lost, sign it out from another device under **Settings → Sessions**.

Element started from the applications menu keeps using the keyring.

## Configuration

`~/.config/nonsteamapps/nonsteamapps.conf` holds one setting, `PROFILE_PER_STEAM_ACCOUNT` (see above). Anything you add to a shortcut's **Launch Options** in Steam after `--steam-account <ID>` is passed to the app, for example `--debug-gpu` for VacuumTube.

## Commands

The installer places the `nonsteamapps` command in `~/.local/share/nonsteamapps/bin/`:

```text
nonsteamapps install [APP...]        install or repair apps and add them to Steam
nonsteamapps remove APP... [--purge] [--keep-app]
                                     remove apps from Steam and uninstall those NonSteamApps installed;
                                     --purge also deletes their data for every Steam account
nonsteamapps list                    every app, and whether it is installed
nonsteamapps update                  update the apps NonSteamApps installed
nonsteamapps steam add|remove|status [APP...] [--user all|auto|ID]
nonsteamapps doctor                  diagnostics, including each app's last launch log
nonsteamapps uninstall [--purge] [--keep-apps]
nonsteamapps launch APP [--steam-account ID] [--verbose] [-- ARGS]
                                     what Steam runs
```

`./uninstall.sh [--purge]` in this repository does the same as `nonsteamapps uninstall`. Without `--purge`, sign-ins and settings are kept.

## Moving from SteamOS YT

Installing NonSteamApps on a device with SteamOS YT, the Helium-based YouTube kiosk this project used to be, does the following:

- **Shortcut:** the existing YouTube shortcut now starts VacuumTube. It keeps its Steam app ID, so its play time, collections, controller layout and resolution setting carry over.
- **Shared sign-in:** if SteamOS YT was set to share one sign-in between Steam accounts, that choice carries over.
- **Clean-up:** after asking, the installer removes SteamOS YT: Helium, its profiles, its settings, its update timer and its menu entry.
- **Signing in again:** Helium's sign-ins cannot move to VacuumTube, so sign in to YouTube once for each Steam account.

## How it works

1. `install.sh` copies the program to `~/.local/share/nonsteamapps` and runs `nonsteamapps install`.
2. Each app is installed from Flathub with `flatpak install --user`, unless it is already installed.
3. Each app gets a link in `~/.local/share/nonsteamapps/apps/`, for example `apps/youtube`, pointing at the launcher. Steam's shortcut runs that link with `--steam-account <ID>`. Steam derives the shortcut's app ID from the link and the name, and NonSteamApps writes the shortcut to each account's `shortcuts.vdf`, with the artwork in the account's `grid` folder.
4. When an app starts, the launcher works out the Steam account: the shortcut's, otherwise the most recent sign-in. It then:
   - prepares that account's data;
   - logs to `~/.local/state/nonsteamapps/<app>.log`;
   - replaces itself with `flatpak run <app> …`.
5. A weekly systemd user timer runs `nonsteamapps update`. Discover updates any other Flatpaks.

## Troubleshooting

- **"Steam is running in Game Mode":** switch to Desktop Mode and run the command again.
- **An app does not start:** `nonsteamapps doctor` shows each app's last launch log; `nonsteamapps launch youtube --verbose` runs it in the terminal.
- **A new Steam account has no shortcuts:** run `nonsteamapps steam add`.
- **The picture looks soft on a TV:** see [On a TV](#on-a-tv-use-its-full-resolution).

## Development

```bash
python3 -m unittest discover -s tests          # apps, Flatpak, Steam, migration and command-line flows with a fake flatpak
shellcheck -x -P SCRIPTDIR install.sh uninstall.sh src/bin/nonsteamapps tests/sandbox.sh
tests/sandbox.sh                               # install.sh, a launch through the link Steam runs, uninstall.sh
node tools/render-artwork.js [APP...]          # render assets/src/<app> into assets/artwork/<app>
```

| Path | Purpose |
| --- | --- |
| `install.sh`, `uninstall.sh` | Entry points (work from a clone or through `curl … \| bash`) |
| `src/bin/nonsteamapps` | Launcher: runs the command-line interface, or starts an app when called through its link |
| `src/lib/nonsteamapps/` | Python standard-library package: `apps.py` (the apps), `flatpak.py`, `steam.py` and `vdf.py` (shortcuts and artwork), `steamclient.py`, `legacy.py` (SteamOS YT), `cli.py` |
| `src/share/` | Default settings and the update timer |
| `assets/src/<app>`, `assets/artwork/<app>` | SVG sources and rendered Steam artwork |
| `tests/fakes/flatpak` | Stand-in for `flatpak`, used by the tests |

To add an app:

1. Add an `App` to `apps.py` with its Flathub ID, arguments and per-account data.
2. Draw its artwork in `assets/src/<app>` and render it.
3. Extend the tests.

## Roadmap

- [ADR 0001](docs/decisions/0001-multi-app-steam-integration.md): why NonSteamApps installs upstream clients from Flathub and owns only the Steam integration.
- [Maximum Game Resolution plan](docs/plans/steam-native-resolution.md): set **Native** for every app and account automatically.
- Steam Input layouts for each app, for example a mouse-and-keyboard layout for Element.

## Acknowledgements

- [VacuumTube](https://github.com/shy1132/VacuumTube) by shy1132 and contributors, which brings YouTube's TV interface to the desktop.
- [Element](https://github.com/element-hq/element-web), and the maintainers of its [Flathub package](https://github.com/flathub/im.riot.Riot).
- [Jellyfin Desktop](https://github.com/jellyfin/jellyfin-desktop) by the Jellyfin project.
- [Steam ROM Manager](https://github.com/SteamGridDB/steam-rom-manager): reference for Steam's shortcut, artwork and controller conventions.

NonSteamApps is not affiliated with Valve, Google, Element, the Matrix.org Foundation or the Jellyfin project. YouTube is a trademark of Google LLC; Steam and SteamOS are trademarks of Valve Corporation; other names belong to their owners. The artwork in this repository is original.
