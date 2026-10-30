import json
import tempfile
import unittest
from pathlib import Path

import _paths  # noqa: F401
from nonsteamapps import apps

HOME = Path("/home/deck")


class RegistryTests(unittest.TestCase):
    def test_ids_and_lookup(self):
        self.assertEqual(apps.ids(), ["youtube", "element", "jellyfin"])
        self.assertEqual(apps.by_id(" YouTube ").flatpak, "rocks.shy.VacuumTube")
        with self.assertRaises(KeyError):
            apps.by_id("netflix")

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

    def test_new_vacuumtube_folders_turn_on_sponsorblock_dearrow_and_dislikes(self):
        youtube = apps.by_id("youtube")
        app_home = youtube.home(self.home)
        youtube.profile.prepare(app_home, 111, lambda options: 0)
        settings = app_home / "config/VacuumTube-steam-111/config.json"
        self.assertEqual(json.loads(settings.read_text()), {"sponsorblock": True, "dearrow": True, "dislikes": True})
        settings.write_text('{"sponsorblock": false}')
        youtube.profile.prepare(app_home, 111, lambda options: 0)
        self.assertEqual(json.loads(settings.read_text()), {"sponsorblock": False})
        youtube.profile.prepare_shared(app_home)
        self.assertTrue(json.loads((app_home / "config/VacuumTube/config.json").read_text())["dearrow"])

    def test_element_folders_start_empty(self):
        element = apps.by_id("element")
        app_home = element.home(self.home)
        element.profile.prepare(app_home, 111, lambda options: 0)
        element.profile.prepare_shared(app_home)
        self.assertEqual(list((app_home / "config/Element-steam-111").iterdir()), [])
        self.assertFalse((app_home / "config/Element").exists())

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
