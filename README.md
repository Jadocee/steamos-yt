# NonSteamApps

Living-room apps for SteamOS, added to the Steam library with original artwork. They come from Flathub, or run in NonSteamApps' own copy of the Helium browser, set up for a TV and a controller. Each Steam account gets its own sign-ins. The apps work in Game Mode and Desktop Mode, and NonSteamApps keeps them up to date.

| In Steam | App | Source | Good to know |
| --- | --- | --- | --- |
| **YouTube** | [VacuumTube](https://github.com/shy1132/VacuumTube) | `rocks.shy.VacuumTube` | YouTube's TV interface, with controller support, ad blocking and casting from the YouTube phone app. NonSteamApps turns on SponsorBlock, DeArrow, dislike counts, the remaining-time display and HDR, hides Shorts and stops the "Continue watching?" prompt. |
| **Element** | [Element Desktop](https://element.io) | `im.riot.Riot` | Matrix chat. A desktop interface: use the touchscreen, the trackpads or a keyboard. |
| **Signal** | [Signal Desktop](https://signal.org/download/) | `org.signal.Signal` | Private messages and calls, linked to Signal on your phone. A desktop interface, like Element. Flathub's package is an unofficial repackaging of Signal's own release. |
| **Jellyfin** | [Jellyfin Desktop](https://github.com/jellyfin/jellyfin-desktop) | `org.jellyfin.JellyfinDesktop` | Your Jellyfin server in its TV layout, with controller support. It plays more formats without the server converting them. |
| **LocalSend** | [LocalSend](https://localsend.org) | `org.localsend.localsend_app` | Send files to and from nearby phones and computers over your own network, with no account and no internet needed. Received files go to `~/Downloads`. |
| **Helium** | [Helium](https://helium.computer) | Signed Helium release | A private web browser with uBlock Origin built in, set up for a TV and a controller. |
| **Prime Video** | Prime Video in Helium | Helium, full screen | Amazon's streaming service, full screen with no browser interface. |
| **HBO Max** | HBO Max in Helium | Helium, full screen | Warner Bros. Discovery's streaming service, full screen with no browser interface. |
| **Netflix** | Netflix in Helium | Helium, full screen | Netflix's streaming service, full screen with no browser interface. |
| **Disney+** | Disney+ in Helium | Helium, full screen | Disney's streaming service, full screen with no browser interface. |
| **ProtonDB** | ProtonDB in Helium | Helium, full screen | Player reports on how well games run with Proton, full screen with no browser interface. |

## Features

- **No root, nothing lost on updates.** Apps install into your user Flatpak installation, which SteamOS updates leave alone. An app you already installed, for example through Discover, is used as it is and never uninstalled. The one step that needs your password is opening LocalSend's port when SteamOS's firewall is on, and NonSteamApps asks first.
- **Every Steam account.** Each account on the device gets a shortcut, with artwork for the library, the capsule, the hero banner, the logo and the icon. The Steam overlay is off.
- **Separate sign-ins.** Each Steam account has its own data in every app except LocalSend, which has no sign-in, so its settings are shared (see [Several Steam accounts](#several-steam-accounts)).
- **Console-ready browser apps.** Helium, the streaming apps and ProtonDB open without first-run pages, prompts or a "Restore pages?" bubble after Steam closes them. The arrow keys move between links and buttons, the interface is dark, and in Game Mode pages are scaled for the TV (see [Helium apps](#helium-apps)).
- **Private by default.** Helium blocks ads and trackers with its built-in uBlock Origin. NonSteamApps' Helium profiles also send Global Privacy Control and keep no crash reports (see [Privacy, security and ad blocking](#privacy-security-and-ad-blocking)).
- **Controller layouts.** YouTube gets Steam's Gamepad controller layout, and the Helium apps, Element, Signal and LocalSend get its Web Browser layout, unless you have picked another.
- **Updates.** A weekly timer updates the apps NonSteamApps installed, Helium included.
- **Replaces SteamOS YT.** On a device with this project's earlier YouTube kiosk, its YouTube shortcut moves to VacuumTube and keeps its place in the library (see [Moving from SteamOS YT](#moving-from-steamos-yt)).

## Requirements

- SteamOS 3, or another Linux system with Steam and Flatpak
- Python 3.8 or newer, `flatpak`, `tar` and `xz`, `gpg` to check Helium's signature, and `curl` to download the installer; all are included with SteamOS
- An internet connection. The first install of each app also downloads its Flatpak runtime or Helium, which takes a while.

## Install

In Desktop Mode, open Konsole and run:

```bash
curl -fsSL https://raw.githubusercontent.com/jadocee/steamos-yt/main/install.sh | bash
```

This installs all eleven apps. To choose, name them:

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
| `--helium-archive FILE` | Install Helium from a downloaded release archive, with its `.asc` signature beside it |
| `--skip-verify` | Install Helium without checking its signature (not recommended) |
| `-y`, `--yes` / `-q`, `--quiet` | Answer yes to questions / print only warnings and errors |

## Using the apps

Open them from **Library → Non-Steam** in Game Mode or in the Steam client in Desktop Mode. To quit, use the app's own exit, or press the Steam button and choose **Exit game**.

- **YouTube:** controllers work out of the box, with Steam's Gamepad layout. Press `Ctrl+O`, or open YouTube's settings, for VacuumTube's settings: ad blocking, SponsorBlock categories, DeArrow, dislikes, hiding Shorts, codec filters and more. Each Steam account's VacuumTube starts set up for a TV: no "Continue watching?" prompt, no Shorts, the time left shown while playing, and HDR allowed. HDR needs an HDR TV, Steam's HDR setting turned on, and VacuumTube running on Wayland; if colours look washed out on a screen without HDR, turn off **Wayland HDR** in VacuumTube's settings. To cast from a phone, choose the device in the YouTube app on the same network. In Game Mode, VacuumTube turns Chromium's sandbox off; `GAME_MODE_SANDBOX=1` keeps it on (see [Configuration](#configuration)).
- **Element:** Element has no controller navigation, so it gets Steam's Web Browser controller layout, in which the trackpads work as a mouse. Use those or the touchscreen; **Steam + X** opens the on-screen keyboard. To pick another layout, use the controller icon on its library page. On a TV in Game Mode, Element is scaled like the Helium apps (`TV_SCALE`). Closing its window quits it: each Steam account's Element starts with minimising to the tray turned off, because Game Mode has no tray to bring it back from.
- **Signal:** on its first start, link it to Signal on your phone: in the phone app, open **Settings → Linked devices** and scan the code on screen. Each Steam account links its own Signal. As with Element, it has Steam's Web Browser controller layout and the TV scale, and closing its window quits it. See [How Signal keeps its data](#how-signal-keeps-its-data).
- **Jellyfin:** starts in its TV layout. Add your server and sign in once for each Steam account.
- **LocalSend:** devices on the same network find each other while LocalSend is open on both. LocalSend listens on port 53317 (TCP and UDP). When SteamOS's firewall (firewalld) is running, the installer offers to open that port, both now and permanently, in every firewall zone in use. `sudo` then asks for your password. Removing LocalSend closes the port again, unless you keep the app with `--keep-app`.
  - **Receiving:** accept a transfer and the files land in `~/Downloads`.
  - **Sending:** you pick files through the system file chooser. If it does not open in Game Mode, send from Desktop Mode.
  - **Controls:** use the touchscreen, or the trackpads in Steam's Web Browser layout.
- **Helium, Prime Video, HBO Max, Netflix, Disney+ and ProtonDB:** see [Helium apps](#helium-apps).

### On a TV: use its full resolution

In Game Mode, Steam decides the resolution each app runs at. On an external display, its default is usually lower than the TV's own. With the Steam Deck connected to the TV, select an app in your library, then **⚙ → Properties → Shortcut → Maximum Game Resolution → Native**. The setting only appears while an external display is connected. Set it for each app, and for each Steam account. [docs/plans/steam-native-resolution.md](docs/plans/steam-native-resolution.md) describes how automating this is planned.

## Several Steam accounts

Each Steam account's shortcut starts the app with `--steam-account <ID>`. NonSteamApps then points the app at that account's own data:

| App | Data for a Steam account |
| --- | --- |
| YouTube | `~/.var/app/rocks.shy.VacuumTube/config/VacuumTube-steam-<ID>` |
| Element | `~/.var/app/im.riot.Riot/config/Element-steam-<ID>` |
| Signal | `~/.var/app/org.signal.Signal/config/Signal-steam-<ID>` |
| Jellyfin | A Jellyfin Desktop profile named `steam-<ID>`, created on first launch |
| LocalSend | Shared by every account: it has no sign-in, and received files go to `~/Downloads` |
| Helium, Prime Video, HBO Max, Netflix, Disney+, ProtonDB | A Helium profile in `~/.local/share/nonsteamapps/profiles/<app>/<ID>` |

Started from the applications menu, VacuumTube, Element and Signal use their usual data instead, and Jellyfin uses its default profile. To give every account the same data, set `PROFILE_PER_STEAM_ACCOUNT=0` in `~/.config/nonsteamapps/nonsteamapps.conf`.

## Helium apps

Helium publishes no Flatpak, so NonSteamApps installs its signed release itself. It checks the signature against Helium's public key, keeps the installed version and the one before it in `~/.local/share/nonsteamapps/helium`, and updates it with the other apps. The apps run as follows:

- **Helium** opens as a full browser, maximised.
- **Prime Video**, **HBO Max**, **Netflix**, **Disney+** and **ProtonDB** each open their site full screen (kiosk mode), with no address bar or tabs. To leave, press the Steam button and choose **Exit game**.

Each app has its own Helium profile for each Steam account, so signing in to one never signs you in to another. Before every start, NonSteamApps sets up that profile for a console:

- **No interruptions:** onboarding and welcome pages are marked as seen, and the last session is recorded as closed cleanly. Steam ends apps by signalling them, which would otherwise bring up "Restore pages?".
- **Fewer prompts:** sites cannot ask to send notifications. The full-screen apps also turn off translation, password and address saving, and permission prompts.
- **Navigation:** the arrow keys move between links and buttons, as on a TV (Chromium's spatial navigation).
- **Dark:** Helium's interface is dark, and so are sites that offer a dark theme. In the Helium app, **Settings → Appearance → Mode** switches back to light.
- **Scale:** in Game Mode, pages are scaled so a TV shows a 720p-sized layout (1.5× at 1080p, 3× at 4K). Set `TV_SCALE` to choose a fixed scale.
- **Video:** decoding uses the graphics chip (VA-API), and video plays without waiting for a click.
- **Controllers:** the apps get Steam's Web Browser controller layout. The trackpads work as a mouse and scroll wheel, and **Steam + X** opens the on-screen keyboard. On the Steam Deck, **L1** and **R1** go back and forward, and the **Menu** button closes a tab. In ProtonDB, links to the Steam store and other sites open in a new tab, so **Menu** brings you back to ProtonDB. Change the layout under the controller icon on the app's library page.

### Streaming apps: what to expect

- **Widevine:** all four services need Widevine copy protection. Helium downloads it through Helium's services the first time a profile asks for it, and every profile then shares that download. If the first video does not play, close the app and open it again.
- **Picture quality:** on Linux, Widevine runs without hardware protection (level L3), and the services limit browsers like this: Prime Video to standard definition, Netflix to 720p. Disney+ plays, but may limit quality too. HBO Max does not officially support Linux, so it may limit quality, or stop playing altogether. NonSteamApps cannot lift these limits.
- **Helium's services:** they are on by default, because they deliver Widevine and keep the ad blocker's filter lists current. Set `HELIUM_SERVICES=0` to keep Helium from contacting them; the streaming apps then cannot play.

### Privacy, security and ad blocking

Helium does most of the work, and NonSteamApps keeps its defaults:

- **Ads and trackers:** uBlock Origin is built in. Helium's services keep its filter lists current.
- **Tracking:** third-party cookies are blocked, and WebRTC does not reveal local network addresses. Fingerprinting scripts get slightly randomised answers. Link-auditing pings, page preloading and running in the background are off.
- **Connections:** Helium tries HTTPS first, and warns before it opens a public site over an insecure connection.
- **Updates:** NonSteamApps installs Helium only with a valid signature from Helium's key, updates it every week, and keeps the version before for `nonsteamapps rollback`.

Each new profile also:

- sends [Global Privacy Control](https://globalprivacycontrol.org), which asks sites not to sell or share your data; some laws, such as California's, require sites to honour it;
- keeps crash reports off, so no upload question appears after a crash.

NonSteamApps sets these only when it creates a profile, so a change you make in Helium's settings stays.

Left out on purpose:

| Not added | Why |
| --- | --- |
| Extra extensions, such as ones claiming 1080p on Netflix | Each is more code from another source with access to your sign-ins, to vet and keep updated. The 1080p ones also rely on tricks that the services break without notice. |
| Strict HTTPS-only mode | Helium already prefers HTTPS. Strict mode adds full-page warnings that are awkward to get past with a controller. |
| A fixed secure-DNS provider | Helium already uses DNS over HTTPS when your network's DNS provider supports it. A fixed provider would see every site you visit, and can break home networks that name local devices or filter content. |
| JavaScript without its optimiser | It removes a common route for exploits, but makes the streaming sites' heavy interfaces noticeably slower. |
| Locking the streaming apps to their own sites | Sign-in, payment and playback span many domains that change without notice, so a lock would break them. |
| Changing uBlock Origin's filter lists | Doing it for you would need a system-wide browser policy, which needs root. You can add lists, such as cookie-notice filters, in uBlock Origin's own settings in the Helium app. |

**Ads in ad-supported plans.** uBlock Origin removes ads and trackers from web pages. The ads in the streaming services' ad-supported plans, however, come from the services themselves, alongside the video, so a blocker either cannot remove them or breaks playback; only an ad-free plan does.

## How Element keeps your sign-in

Element normally protects its stored session secrets with the system keyring. Game Mode has no keyring, and a profile protected by KWallet in Desktop Mode cannot be opened in Game Mode. Steam therefore starts Element with `--password-store=basic --storage-mode=allow-plaintext`.

The session secrets stay in the profile folder, encrypted with a fixed key rather than a password: hidden from casual view, but not protected from software running as your user. In exchange, the same profile works in both modes and Element never stops at a prompt a controller cannot answer.

To limit the risk:

- set up Element's **Secure Backup** with a recovery key;
- if the device is lost, sign it out from another device under **Settings → Sessions**.

Element started from the applications menu keeps using the keyring.

## How Signal keeps its data

Flathub's Signal keeps the key to its message database in plain text by default (`SIGNAL_PASSWORD_STORE=basic`), because of database-corruption bugs with the encrypted keyrings. Game Mode has no keyring anyway, so each Steam account's Signal always uses this store, and the same profile opens in both modes.

On a first start with this store, Flathub's Signal asks for confirmation, with **No**, which quits, preselected. That is easy to answer wrongly with a controller. NonSteamApps skips the question by creating the account's settings file before the first start, and shows the same note after installing instead.

The key can therefore be read by anyone who can read your files. If the device is lost, unlink it from your phone under **Settings → Linked devices**.

Signal started from the applications menu keeps Flathub's own defaults, including the question.

## Configuration

`~/.config/nonsteamapps/nonsteamapps.conf` holds four settings:

| Setting | Default | Effect |
| --- | --- | --- |
| `PROFILE_PER_STEAM_ACCOUNT` | `1` | Separate data for each Steam account (see [Several Steam accounts](#several-steam-accounts)) |
| `HELIUM_SERVICES` | `1` | Let Helium use its services, which deliver Widevine for the streaming apps and keep the ad blocker's filter lists current |
| `TV_SCALE` | `auto` | Scale of the Helium apps, Element and Signal: `auto` sizes them for a TV in Game Mode, or a number such as `1.5`. Replaces `HELIUM_SCALE`, which is still read |
| `GAME_MODE_SANDBOX` | `0` | `1` keeps Chromium's sandbox on for YouTube in Game Mode. Not yet confirmed on a Steam Deck: if YouTube then does not start, set it back to `0` |

Anything you add to a shortcut's **Launch Options** in Steam after `--steam-account <ID>` is passed to the app, for example `--debug-gpu` for VacuumTube.

## Commands

The installer places the `nonsteamapps` command in `~/.local/share/nonsteamapps/bin/`:

```text
nonsteamapps install [APP...]        install or repair apps and add them to Steam
nonsteamapps remove APP... [--purge] [--keep-app]
                                     remove apps from Steam and uninstall those NonSteamApps installed;
                                     --purge also deletes their data for every Steam account
nonsteamapps list                    every app, and whether it is installed
nonsteamapps update                  update the apps NonSteamApps installed, Helium included
nonsteamapps rollback                switch Helium back to the version installed before
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
2. Each Flathub app is installed with `flatpak install --user`, unless it is already installed. The Helium apps share one signed Helium release, unpacked in `~/.local/share/nonsteamapps/helium`.
3. Each app gets a link in `~/.local/share/nonsteamapps/apps/`, for example `apps/youtube`, pointing at the launcher. Steam's shortcut runs that link with `--steam-account <ID>`. Steam derives the shortcut's app ID from the link and the name, and NonSteamApps writes the shortcut to each account's `shortcuts.vdf`, with the artwork in the account's `grid` folder.
4. When an app starts, the launcher works out the Steam account: the shortcut's, otherwise the most recent sign-in. It then:
   - prepares that account's data (for a Helium app, its profile: preferences, a clean last exit and the shared Widevine folder);
   - logs to `~/.local/state/nonsteamapps/<app>.log`;
   - replaces itself with `flatpak run <app> …` (for Signal, `flatpak run --command=env …`, so that Signal's own launch script sees the account's folder), or with Helium and its console flags.
5. For apps with a controller layout, NonSteamApps finds Valve's layout in Steam's `controller_base/templates` and records it for the shortcut in `steamapps/common/Steam Controller Configs/<ID>/config`, where Steam keeps the layout a user picks. It never replaces a layout you chose.
6. If firewalld is running, LocalSend's port is opened with `sudo firewall-cmd`, and NonSteamApps records what it opened so that it can close it again.
7. A weekly systemd user timer runs `nonsteamapps update`. Discover updates any other Flatpaks.

## Troubleshooting

- **"Steam is running in Game Mode":** switch to Desktop Mode and run the command again.
- **An app does not start:** `nonsteamapps doctor` shows each app's last launch log; `nonsteamapps launch youtube --verbose` runs it in the terminal.
- **A new Steam account has no shortcuts:** run `nonsteamapps steam add`.
- **A Helium update misbehaves:** `nonsteamapps rollback` switches back to the previous version.
- **A streaming app shows a playback error the first time:** close the app and open it again, once Widevine has downloaded. `nonsteamapps doctor` shows whether it has.
- **The picture looks soft on a TV:** see [On a TV](#on-a-tv-use-its-full-resolution).
- **YouTube does not start in Game Mode after setting `GAME_MODE_SANDBOX=1`:** set it back to `0`.
- **Phones and computers cannot see the device in LocalSend:** `nonsteamapps doctor` shows whether the firewall lets port 53317 in. If it does not, run the installer again. If opening the port failed because your account has no password, set one first with `passwd`. Also check that your router does not isolate devices from each other, which guest networks often do.
- **Casting from the YouTube app does not find the device:** with the firewall on, casting may be blocked. VacuumTube answers on UDP port 1900 and a TCP port it picks at random each time, so NonSteamApps cannot open a fixed port for it.

## Development

```bash
python3 -m unittest discover -s tests          # apps, Flatpak, Helium (with real signatures), Steam, layouts, migration and command-line flows
shellcheck -x -P SCRIPTDIR install.sh uninstall.sh src/bin/nonsteamapps tests/sandbox.sh tests/fakes/sudo
tests/sandbox.sh                               # install.sh, launches through the links Steam runs, uninstall.sh
node tools/render-artwork.js [APP...]          # render assets/src/<app> into assets/artwork/<app>
```

| Path | Purpose |
| --- | --- |
| `install.sh`, `uninstall.sh` | Entry points (work from a clone or through `curl … \| bash`) |
| `src/bin/nonsteamapps` | Launcher: runs the command-line interface, or starts an app when called through its link |
| `src/lib/nonsteamapps/` | Python standard-library package: `apps.py` (the apps), `flatpak.py`, `helium.py` (the signed Helium release), `browser.py` (console profiles and flags), `display.py` (TV scale), `controllers.py` (Steam layouts), `steam.py` and `vdf.py` (shortcuts and artwork), `steamclient.py`, `firewall.py` (LocalSend's port), `legacy.py` (SteamOS YT), `cli.py` |
| `src/share/` | Default settings, the update timer and Helium's public signing key (fingerprint `BE67 7C19 89D3 5EAB 2C5F 26C9 3516 01AD 01D6 378E`) |
| `assets/src/<app>`, `assets/artwork/<app>` | SVG sources and rendered Steam artwork |
| `tests/fakes/` | Stand-ins for `flatpak`, `firewall-cmd` and `sudo`, used by the tests; `tests/_fakes.py` also builds a stand-in Helium release |

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
- [Signal Desktop](https://github.com/signalapp/Signal-Desktop) by Signal Messenger, and the maintainers of its unofficial [Flathub package](https://github.com/flathub/org.signal.Signal).
- [Jellyfin Desktop](https://github.com/jellyfin/jellyfin-desktop) by the Jellyfin project.
- [LocalSend](https://github.com/localsend/localsend) by Tien Do Nam and contributors.
- [Helium](https://github.com/imputnet/helium) by imput, built on ungoogled-chromium.
- [ProtonDB](https://www.protondb.com), where players report how well games run with Proton.
- [Steam ROM Manager](https://github.com/SteamGridDB/steam-rom-manager): reference for Steam's shortcut, artwork and controller conventions.

NonSteamApps is not affiliated with Valve, Google, Element, the Matrix.org Foundation, Signal Messenger, the Jellyfin project, LocalSend, imput, ProtonDB, Amazon, Warner Bros. Discovery, Netflix or The Walt Disney Company. YouTube is a trademark of Google LLC; Steam and SteamOS are trademarks of Valve Corporation; other names belong to their owners. The artwork in this repository is original.
