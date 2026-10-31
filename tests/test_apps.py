import json
import tempfile
import unittest
from pathlib import Path

import _paths  # noqa: F401
from nonsteamapps import apps

HOME = Path("/home/deck")


class RegistryTests(unittest.TestCase):
    def test_ids_and_lookup(self):
        self.assertEqual(
            apps.ids(),
            ["youtube", "element", "signal", "jellyfin", "localsend", "helium", "primevideo", "hbomax", "netflix", "disneyplus",
             "protondb"],
        )
        self.assertEqual(apps.by_id(" YouTube ").flatpak, "rocks.shy.VacuumTube")
        self.assertEqual(apps.by_id("DisneyPlus").name, "Disney+")
        with self.assertRaises(KeyError):
            apps.by_id("kodi")

    def test_every_app_ships_its_artwork(self):
        artwork = Path(_paths.ROOT) / "assets" / "artwork"
        for app in apps.APPS:
            names = sorted(path.name for path in (artwork / app.id).iterdir())
            self.assertEqual(names, ["capsule.png", "hero.jpg", "icon.png", "logo.png", "wide.png"], app.id)


class ArgumentTests(unittest.TestCase):
    def test_youtube_points_vacuumtube_at_a_folder_per_account(self):
        youtube = apps.by_id("youtube")
        self.assertEqual(
            youtube.arguments(HOME, 111),
            ["--fullscreen", "--portable=/home/deck/.var/app/rocks.shy.VacuumTube/config/VacuumTube-steam-111"],
        )
        self.assertEqual(youtube.arguments(HOME, None), ["--fullscreen"])

    def test_element_keeps_secrets_the_same_way_in_game_and_desktop_mode(self):
        self.assertEqual(
            apps.by_id("element").arguments(HOME, 222),
            ["--password-store=basic", "--storage-mode=allow-plaintext", "--profile=steam-222"],
        )

    def test_localsend_has_no_sign_in_so_every_account_shares_its_settings(self):
        localsend = apps.by_id("localsend")
        self.assertIsNone(localsend.profile)
        self.assertEqual(localsend.arguments(HOME, 111), [])

    def test_helium_apps_run_in_helium_with_the_web_browser_layout(self):
        for app_id, url, kiosk in (("helium", "", False), ("primevideo", "https://www.primevideo.com/", True),
                                   ("hbomax", "https://www.hbomax.com/", True), ("netflix", "https://www.netflix.com/", True),
                                   ("disneyplus", "https://www.disneyplus.com/", True),
                                   ("protondb", "https://www.protondb.com/", True)):
            app = apps.by_id(app_id)
            self.assertEqual((app.flatpak, app.client, app.browser.url, app.browser.kiosk), ("", "Helium", url, kiosk))
            self.assertEqual(app.controller, apps.WEB_BROWSER)
        self.assertEqual(
            [app.id for app in apps.APPS if app.controller == apps.WEB_BROWSER],
            ["element", "signal", "localsend", "helium", "primevideo", "hbomax", "netflix", "disneyplus", "protondb"],
        )
        self.assertEqual([app.id for app in apps.APPS if app.controller == apps.GAMEPAD], ["youtube"])
        self.assertEqual([app.id for app in apps.APPS if not app.controller], ["jellyfin"])

    def test_element_scales_for_a_tv_and_vacuumtube_can_keep_its_sandbox(self):
        self.assertEqual([app.id for app in apps.APPS if app.tv_scale], ["element", "signal"])
        self.assertEqual(
            {app.id: app.sandbox_off_when for app in apps.APPS if app.sandbox_off_when},
            {"youtube": ("SteamGamepadUI",)},
        )

    def test_signal_starts_its_own_script_with_the_accounts_folder_and_plain_key_store(self):
        signal = apps.by_id("signal")
        self.assertEqual(
            signal.arguments(HOME, 111),
            [
                "XDG_CONFIG_HOME=/home/deck/.var/app/org.signal.Signal/config/Signal-steam-111",
                "SIGNAL_PASSWORD_STORE=basic",
                "signal-desktop",
            ],
        )
        self.assertEqual(signal.run_options(111), ["--command=env"])
        self.assertEqual((signal.arguments(HOME, None), signal.run_options(None)), ([], []))
        self.assertEqual(apps.by_id("element").run_options(111), [])

    def test_jellyfin_starts_in_its_tv_layout_with_a_named_profile(self):
        self.assertEqual(apps.by_id("jellyfin").arguments(HOME, 333), ["--tv", "--fullscreen", "--profile=steam-333"])


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_folder_profiles_are_created_and_found_by_pattern(self):
        youtube = apps.by_id("youtube")
        app_home = youtube.home(self.home)
        self.assertEqual(youtube.profile.existing(app_home), [])
        self.assertTrue(youtube.profile.prepare(app_home, 111, lambda options: 0))
        youtube.profile.prepare(app_home, 222, lambda options: 0)
        (app_home / "config" / "VacuumTube").mkdir()
        (app_home / "config" / "VacuumTube-steam-x").mkdir()
        self.assertEqual(
            [path.name for path in youtube.profile.existing(app_home)],
            ["VacuumTube-steam-111", "VacuumTube-steam-222"],
        )

    def test_new_vacuumtube_folders_start_set_up_for_a_tv(self):
        youtube = apps.by_id("youtube")
        app_home = youtube.home(self.home)
        youtube.profile.prepare(app_home, 111, lambda options: 0)
        settings = app_home / "config/VacuumTube-steam-111/config.json"
        self.assertEqual(
            json.loads(settings.read_text()),
            {
                "sponsorblock": True,
                "dearrow": True,
                "dislikes": True,
                "block_continue_watching": True,
                "hide_shorts": True,
                "features_enabled": True,
                "remaining_time_feature": True,
                "wayland_hdr": True,
            },
        )
        settings.write_text('{"sponsorblock": false}')
        youtube.profile.prepare(app_home, 111, lambda options: 0)
        self.assertEqual(json.loads(settings.read_text()), {"sponsorblock": False})
        youtube.profile.prepare_shared(app_home)
        self.assertTrue(json.loads((app_home / "config/VacuumTube/config.json").read_text())["dearrow"])

    def test_new_element_folders_quit_when_the_window_closes(self):
        element = apps.by_id("element")
        app_home = element.home(self.home)
        element.profile.prepare(app_home, 111, lambda options: 0)
        settings = app_home / "config/Element-steam-111/electron-config.json"
        self.assertEqual(json.loads(settings.read_text()), {"minimizeToTray": False})
        settings.write_text('{"minimizeToTray": true}')
        element.profile.prepare(app_home, 111, lambda options: 0)
        self.assertTrue(json.loads(settings.read_text())["minimizeToTray"])
        element.profile.prepare_shared(app_home)
        self.assertFalse((app_home / "config/Element").exists())

    def test_new_signal_folders_skip_the_flatpaks_first_start_question(self):
        signal = apps.by_id("signal")
        app_home = signal.home(self.home)
        signal.profile.prepare(app_home, 111, lambda options: 0)
        settings = app_home / "config/Signal-steam-111/Signal/config.json"
        self.assertEqual(json.loads(settings.read_text()), {})
        settings.write_text('{"key": "secret"}')
        signal.profile.prepare(app_home, 111, lambda options: 0)
        self.assertEqual(json.loads(settings.read_text()), {"key": "secret"})
        signal.profile.prepare_shared(app_home)
        self.assertFalse((app_home / "config/Signal").exists())
        self.assertEqual([path.name for path in signal.profile.existing(app_home)], ["Signal-steam-111"])

    def make_jellyfin_profile(self, app_home, name, folder):
        directory = app_home / "data/jellyfin-desktop/profiles" / folder
        directory.mkdir(parents=True)
        (directory / "profile.json").write_text(json.dumps({"name": name}))
        return directory

    def test_jellyfin_profile_is_created_once_through_the_app(self):
        jellyfin = apps.by_id("jellyfin")
        app_home = jellyfin.home(self.home)
        calls = []

        def run_app(options):
            calls.append(list(options))
            self.make_jellyfin_profile(app_home, options[1], "a1")
            return 0

        self.assertTrue(jellyfin.profile.prepare(app_home, 111, run_app))
        self.assertTrue(jellyfin.profile.prepare(app_home, 111, run_app))
        self.assertEqual(calls, [["--create-profile", "steam-111"]])

    def test_jellyfin_reports_failure_when_the_profile_does_not_appear(self):
        jellyfin = apps.by_id("jellyfin")
        self.assertFalse(jellyfin.profile.prepare(jellyfin.home(self.home), 111, lambda options: 1))

    def test_jellyfin_existing_lists_only_steam_profiles_and_their_caches(self):
        jellyfin = apps.by_id("jellyfin")
        app_home = jellyfin.home(self.home)
        ours = self.make_jellyfin_profile(app_home, "steam-111", "b2")
        self.make_jellyfin_profile(app_home, "Default", "c3")
        (app_home / "data/jellyfin-desktop/profiles/broken").mkdir()
        cache = app_home / "cache/jellyfin-desktop/profiles/b2"
        cache.mkdir(parents=True)
        self.assertEqual(jellyfin.profile.existing(app_home), [ours, cache])


if __name__ == "__main__":
    unittest.main()
