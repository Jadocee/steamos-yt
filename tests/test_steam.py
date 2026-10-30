import dataclasses
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import _paths  # noqa: F401
from steamos_yt import steam, vdf

ACCOUNT = 22202
OTHER = 39734273
EXE = "/home/deck/.local/share/steamos-yt/bin/steamos-yt"


def reference_crc32(data: bytes) -> int:
    crc = 0xFFFFFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0xEDB88320 if crc & 1 else 0)
    return crc ^ 0xFFFFFFFF


def make_steam(home: Path, accounts=(ACCOUNT, OTHER), recent=ACCOUNT) -> Path:
    root = home / ".local/share/Steam"
    for account in accounts:
        (root / "userdata" / str(account) / "config").mkdir(parents=True)
    users = "".join(
        f'"{steam.STEAM_ID64_BASE + account}" {{ "AccountName" "u{account}" '
        f'"MostRecent" "{1 if account == recent else 0}" "Timestamp" "{account}" }}\n'
        for account in accounts
    )
    (root / "config").mkdir(parents=True)
    (root / "config/loginusers.vdf").write_text(f'"users"\n{{\n{users}}}\n')
    (home / ".steam").mkdir()
    (home / ".steam/steam").symlink_to(root)
    return root


def make_artwork(directory: Path) -> Path:
    directory.mkdir(parents=True)
    for name in ("capsule.png", "wide.png", "hero.png", "logo.png", "icon.png"):
        (directory / name).write_bytes(b"\x89PNG fake " + name.encode())
    return directory


def spec(name="YouTube") -> steam.ShortcutSpec:
    return steam.ShortcutSpec(name=name, exe=EXE, start_dir=str(Path(EXE).parent))


class IdTests(unittest.TestCase):
    def test_appid_matches_reference_crc_with_top_bit(self):
        exe, name = '"/usr/bin/foo"', "Foo"
        expected = reference_crc32((exe + name).encode()) | 0x80000000
        self.assertEqual(steam.shortcut_appid(exe, name), expected)
        self.assertGreaterEqual(expected, 0x80000000)

    def test_game_id_and_sign_conversions(self):
        appid = 0x9ABCDEF0
        self.assertEqual(steam.game_id(appid), (appid << 32) | 0x02000000)
        signed = steam.to_signed32(appid)
        self.assertLess(signed, 0)
        self.assertEqual(steam.to_unsigned32(signed), appid)
        self.assertEqual(steam.game_id(signed), steam.game_id(appid))

    def test_quote_helpers(self):
        self.assertEqual(steam.quote("/a b"), '"/a b"')
        self.assertEqual(steam.quote('"/a b"'), '"/a b"')
        self.assertEqual(steam.unquote(' "/a b" '), "/a b")

    def test_logo_position_parsing(self):
        position = steam.LogoPosition.parse("bottomcenter:40:70")
        self.assertEqual(position.to_json()["logoPosition"], {
            "pinnedPosition": "BottomCenter", "nWidthPct": 40.0, "nHeightPct": 70.0,
        })
        with self.assertRaises(steam.SteamError):
            steam.LogoPosition.parse("Middle")
        with self.assertRaises(steam.SteamError):
            steam.LogoPosition.parse("BottomLeft:150")


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.root = make_steam(self.home)

    def tearDown(self):
        self.tmp.cleanup()

    def test_finds_root_through_symlinks(self):
        self.assertEqual(steam.find_steam_root(home=self.home), self.root.resolve())

    def test_returns_none_without_steam(self):
        with tempfile.TemporaryDirectory() as empty:
            self.assertIsNone(steam.find_steam_root(home=Path(empty)))

    def test_account_selection(self):
        self.assertEqual(steam.account_ids(self.root), sorted([ACCOUNT, OTHER]))
        self.assertEqual(steam.most_recent_account(self.root), ACCOUNT)
        self.assertEqual(steam.select_accounts(self.root, "auto"), [ACCOUNT])
        self.assertEqual(steam.select_accounts(self.root, "all"), sorted([ACCOUNT, OTHER]))
        self.assertEqual(steam.select_accounts(self.root, str(steam.STEAM_ID64_BASE + OTHER)), [OTHER])
        with self.assertRaises(steam.SteamError):
            steam.select_accounts(self.root, "12")
        with self.assertRaises(steam.SteamError):
            steam.select_accounts(self.root, "everyone")

    def test_auto_falls_back_to_all_without_login_data(self):
        (self.root / "config/loginusers.vdf").unlink()
        self.assertEqual(steam.select_accounts(self.root, "auto"), sorted([ACCOUNT, OTHER]))


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_steam(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_launch_account_prefers_the_shortcut_hint(self):
        self.assertEqual(steam.launch_account(self.root, str(OTHER)), OTHER)
        self.assertEqual(steam.launch_account(self.root, f" {steam.STEAM_ID64_BASE + OTHER} "), OTHER)
        self.assertEqual(steam.launch_account(None, str(OTHER)), OTHER)

    def test_launch_account_falls_back_to_most_recent_then_sole_account(self):
        for hint in (None, "", "abc", "0", "²", str(2**32)):
            self.assertEqual(steam.launch_account(self.root, hint), ACCOUNT, hint)
        (self.root / "config/loginusers.vdf").unlink()
        self.assertIsNone(steam.launch_account(self.root))
        shutil.rmtree(self.root / "userdata" / str(OTHER))
        self.assertEqual(steam.launch_account(self.root), ACCOUNT)
        self.assertIsNone(steam.launch_account(None))

    def test_account_names_prefer_persona_name(self):
        (self.root / "config/loginusers.vdf").write_text(
            f'"users" {{ "{steam.STEAM_ID64_BASE + ACCOUNT}" {{ "AccountName" "deck" "PersonaName" "Deck Owner" }}\n'
            f'"{steam.STEAM_ID64_BASE + OTHER}" {{ "AccountName" "guest" }} }}\n'
        )
        self.assertEqual(steam.account_names(self.root), {ACCOUNT: "Deck Owner", OTHER: "guest"})

    def test_merge_launch_options_keeps_user_options(self):
        merge = steam.merge_launch_options
        self.assertEqual(merge("", "--steam-account 5"), "--steam-account 5")
        self.assertEqual(merge("--verbose", "--steam-account 5"), "--steam-account 5 --verbose")
        self.assertEqual(merge("LANG=de %command% --verbose", "--steam-account 5"), "LANG=de %command% --steam-account 5 --verbose")
        self.assertEqual(merge("--steam-account=9 --verbose --steam-account 7", "--steam-account 5"), "--steam-account 5 --verbose")
        self.assertEqual(merge("%command% --steam-account 5", "--steam-account 5"), "%command% --steam-account 5")
        self.assertEqual(merge("--steam-account 9 --verbose", ""), "--verbose")
        self.assertEqual(merge("--steam-accounts 9", "--steam-account 5"), "--steam-account 5 --steam-accounts 9")


class ShortcutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.root = make_steam(self.home)
        self.artwork = make_artwork(self.home / "art")
        self.config = steam.config_dir(self.root, ACCOUNT)

    def tearDown(self):
        self.tmp.cleanup()

    def load_entries(self, account=ACCOUNT):
        data = (steam.config_dir(self.root, account) / "shortcuts.vdf").read_bytes()
        return vdf.loads_binary(data).get("shortcuts")

    def add(self, **kwargs):
        options = dict(
            artwork=steam.collect_artwork(self.artwork),
            logo_position=steam.LogoPosition("BottomLeft", 45, 60),
        )
        options.update(kwargs)
        return steam.add_shortcut(self.root, [ACCOUNT], options.pop("spec", spec()), **options)

    def test_adds_entry_with_steam_layout(self):
        [result] = self.add()
        self.assertTrue(result.created)
        self.assertEqual(result.appid, steam.shortcut_appid(f'"{EXE}"', "YouTube"))
        entries = self.load_entries()
        self.assertEqual(list(entries), ["0"])
        entry = entries.get("0")
        self.assertEqual(entry.type_of("appid"), vdf.INT32)
        self.assertEqual(steam.to_unsigned32(entry.get("appid")), result.appid)
        self.assertEqual(entry.get("Exe"), f'"{EXE}"')
        self.assertEqual(entry.get("StartDir"), f'"{Path(EXE).parent}"')
        self.assertEqual(entry.get("AllowDesktopConfig"), 1)
        self.assertEqual((entry.get("AllowOverlay"), entry.type_of("AllowOverlay")), (0, vdf.INT32))
        self.assertEqual(entry.get("icon"), str(self.config / "grid" / f"{result.appid}_icon.png"))
        self.assertIsInstance(entry.get("tags"), vdf.KeyValues)
        self.assertFalse((steam.config_dir(self.root, OTHER) / "shortcuts.vdf").exists())

    def test_artwork_names_and_logo_position(self):
        [result] = self.add()
        grid = self.config / "grid"
        names = sorted(path.name for path in grid.iterdir())
        appid = result.appid
        self.assertEqual(names, sorted([
            f"{appid}p.png", f"{appid}.png", f"{appid}_hero.png",
            f"{appid}_logo.png", f"{appid}_icon.png", f"{appid}.json",
        ]))
        position = json.loads((grid / f"{appid}.json").read_text())
        self.assertEqual(position["nVersion"], 1)
        self.assertEqual(position["logoPosition"]["pinnedPosition"], "BottomLeft")
        self.assertEqual((grid / f"{appid}p.png").read_bytes(), (self.artwork / "capsule.png").read_bytes())

    def test_stale_artwork_with_other_extensions_is_replaced(self):
        [result] = self.add()
        grid = self.config / "grid"
        stale = grid / f"{result.appid}_hero.jpg"
        stale.write_bytes(b"old")
        self.add()
        self.assertFalse(stale.exists())

    def test_reinstall_updates_in_place_and_keeps_user_rename(self):
        [first] = self.add()
        shortcuts = steam.ShortcutsFile.load(self.config / "shortcuts.vdf")
        shortcuts.find(EXE)[0].set("AppName", "My Tube")
        shortcuts.save()
        [second] = self.add(spec=spec("YouTube"), rename=False)
        self.assertFalse(second.created)
        self.assertEqual(second.appid, first.appid)
        self.assertEqual(second.name, "My Tube")
        [third] = self.add(spec=spec("YouTube TV"), rename=True)
        self.assertEqual(third.name, "YouTube TV")
        self.assertEqual(third.appid, first.appid)
        self.assertEqual(len(self.load_entries()), 1)

    def test_preserves_other_shortcuts_and_matches_steam_casing(self):
        foreign = vdf.KeyValues()
        foreign.set("appid", -5, vdf.INT32)
        foreign.set("appname", "Emulator")
        foreign.set("exe", '"/usr/bin/emu"')
        foreign.set("CustomField", 1234, vdf.UINT64)
        ours = vdf.KeyValues()
        ours.set("appid", steam.to_signed32(0x80000123), vdf.INT32)
        ours.set("appname", "Old name")
        ours.set("exe", f'"{EXE}"')
        root = vdf.KeyValues()
        shortcuts = vdf.KeyValues()
        shortcuts.set("0", foreign, vdf.MAP)
        shortcuts.set("1", ours, vdf.MAP)
        root.set("shortcuts", shortcuts, vdf.MAP)
        (self.config / "shortcuts.vdf").write_bytes(vdf.dumps_binary(root))

        [result] = self.add(rename=False)
        self.assertEqual(result.appid, 0x80000123)
        entries = self.load_entries()
        self.assertEqual(list(entries), ["0", "1"])
        self.assertEqual(entries.get("0").get("CustomField"), 1234)
        self.assertEqual(entries.get("0").type_of("CustomField"), vdf.UINT64)
        self.assertEqual(list(entries.get("1"))[:3], ["appid", "appname", "exe"])
        self.assertEqual(entries.get("1").get("AppName"), "Old name")

    def test_duplicates_are_collapsed(self):
        shortcuts = steam.ShortcutsFile.load(self.config / "shortcuts.vdf")
        shortcuts.upsert(spec())
        shortcuts.shortcuts.set("1", steam._new_entry(0x80000001, spec("Dupe")), vdf.MAP)
        shortcuts.save()
        self.add()
        self.assertEqual(len(self.load_entries()), 1)

    def test_remove_renumbers_and_deletes_artwork(self):
        other = steam.ShortcutSpec(name="Other", exe="/usr/bin/other", start_dir="/usr/bin")
        steam.add_shortcut(self.root, [ACCOUNT], other)
        [result] = self.add()
        steam.add_shortcut(self.root, [ACCOUNT], steam.ShortcutSpec("Third", "/usr/bin/third", "/usr/bin"))
        removed = steam.remove_shortcut(self.root, [ACCOUNT, OTHER], EXE)
        self.assertEqual([item.appid for item in removed], [result.appid])
        self.assertEqual(len(removed[0].artwork), 6)
        entries = self.load_entries()
        self.assertEqual(list(entries), ["0", "1"])
        self.assertEqual([entries.get(key).get("AppName") for key in entries], ["Other", "Third"])
        self.assertEqual(list((self.config / "grid").iterdir()), [])
        self.assertTrue((self.config / ("shortcuts.vdf" + steam.BACKUP_SUFFIX)).exists())

    def test_status_reports_installed_accounts(self):
        self.assertEqual(steam.shortcut_status(self.root, [ACCOUNT, OTHER], EXE), [])
        [result] = self.add()
        [status] = steam.shortcut_status(self.root, [ACCOUNT, OTHER], EXE)
        self.assertEqual((status.account, status.appid, status.name), (ACCOUNT, result.appid, "YouTube"))

    def test_refresh_turns_the_steam_overlay_off(self):
        self.add()
        shortcuts = steam.ShortcutsFile.load(self.config / "shortcuts.vdf")
        shortcuts.find(EXE)[0].set("AllowOverlay", 1, vdf.INT32)
        shortcuts.save()
        self.add()
        self.assertEqual(self.load_entries().get("0").get("AllowOverlay"), 0)

    def test_launch_options_name_each_account_and_keep_user_options(self):
        options = dataclasses.replace(spec(), launch_options=f"--steam-account {steam.ACCOUNT_PLACEHOLDER}")
        steam.add_shortcut(self.root, [ACCOUNT, OTHER], options)
        for account in (ACCOUNT, OTHER):
            self.assertEqual(self.load_entries(account).get("0").get("LaunchOptions"), f"--steam-account {account}")
        shortcuts = steam.ShortcutsFile.load(self.config / "shortcuts.vdf")
        shortcuts.find(EXE)[0].set("LaunchOptions", f"LANG=de %command% --steam-account {OTHER}")
        shortcuts.save()
        steam.add_shortcut(self.root, [ACCOUNT], options)
        self.assertEqual(self.load_entries().get("0").get("LaunchOptions"), f"LANG=de %command% --steam-account {ACCOUNT}")

    def test_corrupt_file_is_reported(self):
        (self.config / "shortcuts.vdf").write_bytes(b"\x00shortcuts\x00\x01broken")
        with self.assertRaises(steam.SteamError):
            self.add()


if __name__ == "__main__":
    unittest.main()
