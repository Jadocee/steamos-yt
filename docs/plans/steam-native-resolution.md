# Plan: set Maximum Game Resolution to Native automatically

**Status:** to do · **Approach:** find the stored key by diffing Steam's files (option 1) · **Fallback:** Steam's client API (option 2)

## Goal

In Game Mode on an external display, Steam runs a shortcut below the TV's resolution unless the shortcut's **Maximum Game Resolution** is set to **Native**. Today every user has to set it by hand, for each app and each Steam account, under **⚙ → Properties → Shortcut**. The installer should set it for every app and account on the device, and the uninstaller should put it back.

It is a per-app setting of the shared Steam integration layer ([ADR 0001](../decisions/0001-multi-app-steam-integration.md)): YouTube and Jellyfin want **Native** on a TV; Element can stay at the default.

## What is known

| Fact | Evidence |
| --- | --- |
| The Steam UI writes the value with `SteamClient.Apps.SetAppResolutionOverride(appId, value)`. The value is `"Default"`, `"Native"` or a `"<width>x<height>"` string. | Steam's extracted UI code (`ClientExtracted/steamui/sp.js` in SteamDatabase/SteamTracking) |
| Steam reads it back from `appDetails.strResolutionOverride`; when it is unset, the UI shows `"Default"`. | Same file |
| On a device with a built-in screen, a separate **Apply to internal display** toggle (`bOverrideInternalResolution`, set with `SteamClient.Apps.ToggleOverrideResolutionForInternalDisplay`) decides whether the override also applies to that screen. | Same file |
| Non-Steam shortcuts show the setting on the **Shortcut** page. Steam games show it on **General**. The control is hidden while Steam has no resolutions to offer, for example with no external display connected. | Same file |
| Steam keeps other per-shortcut client settings in `userdata/<account>/config/localconfig.vdf` under `UserLocalConfigStore → apps → <shortcut app ID>`. Steam ROM Manager writes `UseSteamControllerConfig` there. | Steam ROM Manager, `src/lib/controller-manager.ts` |
| Steam rewrites its configuration files on exit. Edits only survive if Steam is closed while they are made. | Existing behaviour of `shortcuts.vdf`, handled by `steamclient.closed()` in `src/lib/nonsteamapps/steamclient.py` |

Where Steam stores the per-app override is **not** known. The candidates, most likely first:

1. `userdata/<account>/config/localconfig.vdf` → `UserLocalConfigStore → apps → <app ID>`;
2. somewhere else in the same file;
3. `config/config.vdf`, which is shared by every account on the device;
4. Steam Cloud-backed storage under `userdata/<account>/config/cloudstorage/`, which other devices could overwrite.

The device-wide default under **Settings → Display** must not be touched, because it applies to every game.

## Step 1: find the key (manual, once, on a Steam Deck)

1. In Desktop Mode, list the accounts and the shortcut's app ID:

   ```bash
   ~/.local/share/nonsteamapps/bin/nonsteamapps steam status youtube
   # Steam account alpha (12345678): present "YouTube" (app ID 3456789012)
   ```

2. Take snapshots for one account (replace `12345678`):

   ```bash
   STEAM=~/.local/share/Steam
   cp -a "$STEAM/userdata/12345678/config" ~/steam-before-userconfig
   cp -a "$STEAM/config/config.vdf" ~/steam-before-config.vdf
   ```

3. Return to Game Mode with the TV connected. Set YouTube's **⚙ → Properties → Shortcut → Maximum Game Resolution** to **Native**, then switch back to Desktop Mode so that Steam writes its files.
4. Compare:

   ```bash
   diff -ru ~/steam-before-userconfig "$STEAM/userdata/12345678/config"
   diff ~/steam-before-config.vdf "$STEAM/config/config.vdf"
   ```

   Ignore play-time and timestamp churn. Look for `Native`, `Resolution` or the app ID.
5. Repeat with **Default** and with a fixed resolution to learn how the value is written and how it is removed. Repeat with **Apply to internal display** switched on.
6. Record the file, the key path, the value format and whether unset means absent or `"Default"`. Share only those lines, because these files also hold friends lists and other personal data.

If nothing changes in any file, the value is probably in Steam Cloud storage or held only in memory; switch to [option 2](#fallback-option-2-steams-client-api).

## Step 2: implement

1. **VDF:** `vdf.loads_text` already parses text VDF. Add `dumps_text`, which writes keys in their original order with Steam's quoting and escaping. Test it by round-tripping a real `localconfig.vdf` from a Deck byte for byte.
2. **Write the key:** add `steam.set_resolution_override(root, account, appid, value)`. It writes to a temporary file in the same folder, parses the result back, keeps one backup and only then replaces the original. It leaves every other key untouched. Mark the entry as ours, as Steam ROM Manager does with `srmAppId`, so that removal never deletes a value the user chose.
3. **Every account:** reuse `steam.account_ids` and the existing loop over `--user all|auto|ID`. Run only while Steam is closed, inside the same stop and restart window as the shortcut update.
4. **Setting:** give each `App` in `apps.py` a `resolution` (`native` for YouTube and Jellyfin), and add `GAME_RESOLUTION=auto|keep` to `nonsteamapps.conf`, where `auto` applies each app's value and `keep` never touches the key. Add an internal-display setting only if Step 1 shows that the toggle is stored separately.
5. **Commands:** add `nonsteamapps steam resolution [native|default|WxH] [APP…] [--user …]`. `doctor` reports each account's current value. `uninstall` removes the key only where it is still marked as ours.
6. **Tests:** unit tests for the text VDF round trip, escaping, idempotence, several accounts, a missing `apps` section, removal on uninstall, a value the user changed, and refusal while Steam is running. Extend the sandboxed install with fake `userdata` folders, as the existing Steam tests do.
7. **Docs:** replace the manual instructions in the README with the automatic behaviour and the `keep` option. Remove the `TV:` hint from the install summary.

## Step 3: verify on hardware

On a Steam Deck docked to a 4K TV, after a fresh install with two Steam accounts:

- [ ] each account shows **Native** under Properties without any manual step;
- [ ] YouTube and Jellyfin render at the TV's resolution, and YouTube offers 2160p;
- [ ] the value survives a Steam restart, a reboot, a Steam client update and a sign-in on a second device with cloud sync on;
- [ ] undocked, the internal display behaves as the toggle says;
- [ ] uninstalling restores **Default**, and a value the user set by hand is left alone.

## Risks and safeguards

- **Corrupting `localconfig.vdf`** would reset the user's Steam settings. Safeguards: atomic replace, parse-back check, a single rotating backup and a byte-for-byte round-trip test.
- **Cloud sync or a client update overwrites the value.** Detect this by reading the value back after Steam restarts; warn and fall back to the README instructions. Never fail an install on this step.
- **Steam renames the key.** Keep the key path in one constant and have `doctor` report when it is missing.

## Fallback: option 2, Steam's client API

Call `SteamClient.Apps.SetAppResolutionOverride(appId, "Native")` inside the running Steam client through its Chromium Embedded Framework (CEF) debugging port, as Decky Loader does. This is independent of how the value is stored. However, it depends on Steam's internal JavaScript API. It also needs remote debugging switched on, which lets any local process drive Steam. If used, switch debugging on only for the duration of the call and off again afterwards.
