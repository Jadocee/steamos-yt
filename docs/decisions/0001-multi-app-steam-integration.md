# ADR 0001: Become a Steam integration installer for several apps

- **Status:** accepted, 30 October 2026
- **Covers:** how apps are delivered, the shared Steam integration layer and YouTube's engine
- **Related:** [Maximum Game Resolution plan](../plans/steam-native-resolution.md)

## Context

SteamOS YT installs one app, YouTube's TV interface in a Helium kiosk. It integrates it with Steam: a shortcut for every account, artwork, a launch option that identifies the Steam account, separate sign-ins per account and the overlay switched off. Much of the code, however, serves YouTube itself rather than Steam: the Cobalt identity, ad removal, SponsorBlock, DeArrow, Return YouTube Dislike and the site lock.

The goal is now an installation script that handles Steam integration for several apps, starting with YouTube, Element (Matrix) and Jellyfin. SteamOS shapes the answer in three ways:

- The root filesystem is read-only. Valve warns that anything installed outside Flatpak, for example with pacman, may be wiped by the next update [1].
- Game Mode is a Gamescope session, not a desktop. There is one fullscreen app at a time, controllers go through Steam Input, and desktop services such as a keyring cannot be assumed.
- Several Steam accounts can share a device, and each should keep its own sign-ins.

## Decision drivers

1. Maintain the integration, not the apps.
2. Survive SteamOS updates without root access.
3. Offer the best TV and controller experience each app has.
4. Keep data separate per Steam account.
5. Keep sandboxing and get browser-engine security fixes promptly.
6. Stay testable without a Steam Deck.

## What the candidate apps offer

| | YouTube: VacuumTube 2.0.1 [2] | Element Desktop 1.12 [3] | Jellyfin Desktop 2.0 [4] |
| --- | --- | --- | --- |
| Engine | Electron 44 | Electron | Qt 6 WebEngine with libmpv |
| Flathub | `rocks.shy.VacuumTube`, the install its author recommends | `im.riot.Riot`, a community repackaging of Element's own tarball | `org.jellyfin.JellyfinDesktop`, linked from the project's README |
| Other Linux builds | AppImage, deb, tarball | deb, tarball | nightly AppImage |
| TV and controller | YouTube's TV interface; controller and touch support; casting from the YouTube phone app (DIAL) | Desktop interface; touch, or Steam Input acting as mouse and keyboard | TV layout, chosen automatically when the Flatpak runs on SteamOS; SDL controller input |
| Per-account switch | `--portable <dir>` | `--profile <name>` or `--profile-dir <dir>` | `--profile <name>` |
| Game Mode behaviour | Detects Game Mode, forces fullscreen and adds `--no-sandbox` | Keeps secrets in a keyring. Without one, it asks to fall back to `basic_text`, which encrypts with a fixed key | Plays more formats without server transcoding, which is the reason to prefer it to the web client |
| Updates under Flatpak | Flathub; its own updater stands down | Flathub | Flathub; last release December 2025 |

## Options considered

1. **Helium for everything.** One engine, and the site lock and per-account profiles already exist. However, YouTube's TV quirks would remain ours to chase. Jellyfin's web client also leaves more transcoding to the server, and Element's web client cannot search encrypted rooms.
2. **Upstream clients from Flathub, with Helium for web-only apps.** Chosen.
3. **Our own Electron wrappers.** Full control, but every wrapper bundles a Chromium we would have to patch, and it repeats work that upstreams already do. Rejected.
4. **Self-managed AppImages or tarballs for every app.** Works without Flatpak, but makes us responsible for updates, signature checks and rollback for each app. Used only where no Flatpak exists, as with Helium today.
5. **A Decky Loader plugin instead of an installer.** It gets live access to Steam's client API, for collections and resolution, without restarting Steam. However, it depends on a third-party loader that Steam updates can break. It may become an optional companion later; it is not the core.
6. **Building on an existing integrator.** Steam ROM Manager [6] is a desktop app that adds emulated games and other launchers' libraries to Steam. NonSteamLaunchers [5] installs game launchers and browser kiosk shortcuts, YouTube's TV interface among them. Neither separates sign-ins per Steam account or carries per-app Game Mode fixes. We follow their file conventions and never touch entries they own.

## Decision

1. **Scope.** The project becomes a Steam integration installer for living-room apps on SteamOS. YouTube is the first app, not the product.
2. **Shape.** The project has a core, one declarative recipe per app, and interchangeable install backends:
   - The **core** owns everything to do with Steam: shortcuts for every account, artwork, launch options carrying the Steam account, the overlay, Steam Input, Maximum Game Resolution, updates, `doctor` and uninstall.
   - A **recipe** says what to install and how to launch it, including the app's per-account switch and its Game Mode fixes.
   - There are three **backends**:
     - `flatpak` is the default: Flathub, installed per user, with no root access needed;
     - `webapp` is today's Helium kiosk, generalised;
     - `archive` covers signed upstream archives, only where no Flatpak exists.
3. **Choosing a client.** Prefer the upstream-maintained client on Flathub when it does something a browser kiosk cannot: wider codec support, platform features or a maintained TV interface. Otherwise, use `webapp`. Never install with pacman, and never write our own Electron wrapper.
4. **Electron.** The toolkit is not the criterion; upstream maintenance and capability are. An Electron app is acceptable when it is the upstream's own client (Element) or a maintained, purpose-built one (VacuumTube). Each recipe documents the app's security trade-offs.
5. **YouTube.** VacuumTube becomes the default YouTube engine. Today's Helium engine stays as an opt-in `youtube-helium` recipe for one minor release after the switch. After that, its YouTube-specific code is removed unless hardware testing shows a gap that matters. Helium stays as the `webapp` engine.
6. **Stable identity.** The YouTube shortcut keeps its executable path and name when the engine changes. Steam derives the app ID from these two, and play time, artwork, controller layout and resolution are all stored against that ID.
7. **Accounts.** Every recipe keeps data per Steam account through the app's own switch. Today's rule still applies: the first launch inherits any existing shared data.

## Why VacuumTube for YouTube

| | Helium and companion extension (today) | VacuumTube |
| --- | --- | --- |
| Who tracks changes to YouTube's TV interface | This project alone | An active upstream with outside contributors (2.0.1, October 2026) |
| Ads, SponsorBlock, DeArrow, dislike counts | Yes | Yes |
| Further features | None | Casting from the phone app, hiding Shorts, a codec filter, uncapped resolution, settings inside YouTube's interface, userstyles, touch |
| Separate sign-ins per Steam account | Built in | `--portable <dir>`, passed by our launcher |
| Site lock | Yes | No. Sign-in uses a code entered on a phone or computer, so the app has little reason to leave YouTube |
| Sandboxing | Chromium sandbox on; extension code in isolated worlds | Context isolation and the renderer sandbox off; the Chromium sandbox also off in Game Mode. The Flatpak sandbox still confines it: no home-folder access, but all devices and the network |
| Browser-engine security fixes | Helium follows Chromium releases | Arrive when VacuumTube ships a release with a newer Electron |
| Updates | Our signed-update timer | Flathub |

VacuumTube wins on what matters most for this project: it moves the most fragile, fastest-changing work upstream and adds features we would never build. What it gives up is defence in depth. The opt-in `youtube-helium` recipe keeps that available during the overlap. Making the sandbox work in Game Mode is a good first upstream contribution.

## Recipes

Recipes are TOML files, read with `tomllib`. This raises the Python baseline from 3.8 to 3.11, so check the version shipped with SteamOS stable first; if it is older, use JSON with the same fields. `{account}` is the Steam account ID, and `{app_home}` is the app's own folder (for a Flatpak, `~/.var/app/<id>`).

```toml
id = "youtube"
name = "YouTube"

[install]
backend = "flatpak"
app = "rocks.shy.VacuumTube"

[launch]
args = ["--fullscreen"]
account_args = ["--portable={app_home}/config/VacuumTube-steam-{account}"]

[steam]
overlay = false
input = "gamepad"
resolution = "native"
artwork = "artwork/youtube"
```

The other two recipes differ only in their fields:

| Recipe | `install` | `launch.args` | `launch.account_args` | `steam.input` |
| --- | --- | --- | --- | --- |
| `jellyfin` | `flatpak`, `org.jellyfin.JellyfinDesktop` | `--tv`, `--fullscreen` | `--profile=steam-{account}` | `gamepad` |
| `element` | `flatpak`, `im.riot.Riot` | `--password-store=basic` | `--profile=steam-{account}` | `mouse` |
| `youtube-helium` | `webapp`, `https://www.youtube.com/tv`, with today's site list and extension | today's flags | today's profiles | `gamepad` |

Steam runs the core's launcher, never the app directly: `<launcher> launch <recipe> --steam-account <id>`. The launcher picks the account's data folder, lets the first launch inherit shared data, applies the recipe's fixes, and then replaces itself with the app, for example `flatpak run rocks.shy.VacuumTube …`.

`steam.input` becomes `UseSteamControllerConfig` in `localconfig.vdf`, and, when a template is named, an entry in `configset_controller_<type>.vdf`, as Steam ROM Manager writes them [6]. The template file names still need to be confirmed on a Deck.

## Consequences

- **Gains.** The YouTube-specific extension modules, Cobalt identity and their smoke tests stop being ours, which is most of the code that breaks when YouTube changes. New apps cost a recipe rather than a fork. Updates come from Flathub, and Flatpak can roll back with `flatpak update --commit=<commit>`.
- **Costs.** We inherit each upstream's bugs, release pace and security posture. Element arrives through a community Flatpak. Switching YouTube's engine means signing in again once per account. Flatpak runtimes use disk space: Electron, Qt WebEngine and Freedesktop bases.
- **Testing.** Helium smoke tests remain for `webapp`. Unit tests drive a fake `flatpak` command to check arguments, per-account folders and data inheritance. Each app gets a short Game Mode checklist on real hardware: controller, exit, sleep and resume, sign-in persistence, keyring and resolution.

## Migration

| Phase | Work | Done when |
| --- | --- | --- |
| 1. Core | Recipe loader; today's YouTube moves into a `youtube-helium` recipe; `install`, `remove` and `list` per app | No visible change; every existing test and the smoke test pass |
| 2. Flatpak | Per-user Flathub remote; install, update, remove and rollback; launch with per-account folders and data inheritance | Fake-`flatpak` tests pass; `doctor` reports each app's version |
| 3. Apps | Opt-in `youtube` (VacuumTube), `jellyfin` and `element` recipes, with artwork | Each passes its Game Mode checklist on a Steam Deck |
| 4. Steam settings | Steam Input per recipe; Maximum Game Resolution per [the plan](../plans/steam-native-resolution.md) | Settings appear for every account and are removed on uninstall |
| 5. Switch | `youtube` becomes the default; existing installs keep the same shortcut and sign in again | No regression from the checklist; users told in the README and install summary |
| 6. Clean-up | Remove the YouTube-specific Helium code one minor release later; decide the project's name | Only the `webapp` engine remains in Helium |

## Open questions

1. Keep the name `steamos-yt`, or rename the project and command once it serves several apps? Renaming must keep YouTube's old executable path as a shim (see decision 6).
2. Should `youtube-helium` stay permanently for its stronger sandbox and site lock?
3. Is `basic_text` secret storage acceptable for Steam-launched Element profiles? Game Mode may offer no keyring, and the same profile must open in both modes.
4. Which apps come after these three?
5. Should artwork stay original and shipped with each recipe, as today, or be fetched from SteamGridDB with the user's own API key?

## Sources

1. [Steam Support: Steam Deck Desktop FAQ](https://help.steampowered.com/faqs/view/671A-4453-E8D2-323C)
2. VacuumTube: [repository and README](https://github.com/shy1132/VacuumTube); `src/index.js` for Game Mode detection, `--no-sandbox` and window preferences; [Flathub manifest](https://github.com/flathub/rocks.shy.VacuumTube) for permissions; [GamingOnLinux on VacuumTube for Steam Deck](https://www.gamingonlinux.com/2025/06/vacuumtube-is-the-best-way-to-watch-youtube-on-steam-deck-steamos/)
3. Element Desktop, now in [element-web under `apps/desktop`](https://github.com/element-hq/element-web): `src/args.ts` for `--profile`, `--profile-dir` and `--storage-mode`, and `src/store.ts` for the keyring fallback; [Flathub `im.riot.Riot`](https://github.com/flathub/im.riot.Riot)
4. [Jellyfin Desktop](https://github.com/jellyfin/jellyfin-desktop): `src/main.cpp` for its options and `src/system/SystemComponent.cpp` for SteamOS detection; [Flathub](https://flathub.org/apps/org.jellyfin.JellyfinDesktop); [AlternativeTo on the 2.0 release](https://alternativeto.net/news/2025/12/jellyfin-desktop-2-0-launches-with-rebranding-qt-6-upgrade-and-fresh-features)
5. [NonSteamLaunchers](https://github.com/moraroy/NonSteamLaunchers-On-Steam-Deck)
6. [Steam ROM Manager](https://github.com/SteamGridDB/steam-rom-manager), `src/lib/controller-manager.ts`
