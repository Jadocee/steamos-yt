import json
import os
import tempfile
import unittest
from pathlib import Path

import _paths  # noqa: F401
from nonsteamapps import browser


class PreferencesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.profile = Path(self.tmp.name) / "profile"
        self.preferences = self.profile / "Default" / "Preferences"

    def tearDown(self):
        self.tmp.cleanup()

    def read(self):
        return json.loads(self.preferences.read_text())

    def test_new_full_screen_profiles_skip_onboarding_and_prompts(self):
        browser.write_preferences(self.profile, services=True, kiosk=True)
        data = self.read()
        self.assertTrue(data["helium"]["completed_onboarding"])
        self.assertEqual(data["helium"]["services"], {"enabled": True, "user_consented": True, "schema_version": 1})
        self.assertEqual(data["profile"]["exit_type"], "Normal")
        self.assertFalse(data["translate"]["enabled"])
        self.assertFalse(data["credentials_enable_service"])
        self.assertEqual(data["profile"]["default_content_setting_values"], {"notifications": 2, "geolocation": 2})

    def test_the_browser_keeps_its_password_manager_and_translation(self):
        browser.write_preferences(self.profile, services=True, kiosk=False)
        data = self.read()
        self.assertNotIn("translate", data)
        self.assertNotIn("credentials_enable_service", data)
        self.assertEqual(data["profile"]["default_content_setting_values"], {"notifications": 2})

    def test_later_starts_mark_a_clean_exit_and_keep_the_users_choices(self):
        browser.write_preferences(self.profile, services=True, kiosk=True)
        data = self.read()
        data["translate"]["enabled"] = True
        data["profile"]["exit_type"] = "Crashed"
        data["helium"]["services"]["schema_version"] = 3
        self.preferences.write_text(json.dumps(data))
        browser.write_preferences(self.profile, services=False, kiosk=True)
        data = self.read()
        self.assertTrue(data["translate"]["enabled"])
        self.assertEqual((data["profile"]["exit_type"], data["profile"]["exited_cleanly"]), ("Normal", True))
        self.assertFalse(data["helium"]["services"]["enabled"])
        self.assertEqual(data["helium"]["services"]["schema_version"], 3)

    def test_a_corrupt_file_is_kept_aside(self):
        self.preferences.parent.mkdir(parents=True)
        self.preferences.write_text("{broken")
        browser.write_preferences(self.profile, services=True, kiosk=True)
        self.assertEqual(self.preferences.with_name("Preferences.corrupt").read_text(), "{broken")
        self.assertTrue(self.read()["helium"]["completed_onboarding"])


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.profile = self.dir / "profile"
        self.profile.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_lock_left_by_a_closed_helium_is_cleared(self):
        (self.profile / "SingletonLock").symlink_to("steamdeck-999999999")
        (self.profile / "SingletonSocket").symlink_to("/tmp/gone/socket")
        self.assertTrue(browser.clear_stale_lock(self.profile))
        self.assertFalse(os.path.lexists(self.profile / "SingletonLock"))
        self.assertFalse(os.path.lexists(self.profile / "SingletonSocket"))
        self.assertFalse(browser.clear_stale_lock(self.profile))

    def test_every_profile_shares_one_widevine_folder(self):
        shared = self.dir / "helium" / "WidevineCdm"
        browser.link_widevine(self.profile, shared)
        self.assertEqual((self.profile / "WidevineCdm").resolve(), shared.resolve())
        shared.rmdir()
        browser.link_widevine(self.profile, shared)
        self.assertTrue(shared.is_dir())
        other = self.dir / "other"
        (other / "WidevineCdm").mkdir(parents=True)
        browser.link_widevine(other, shared)
        self.assertFalse((other / "WidevineCdm").is_symlink())


class ScaleAndFlagTests(unittest.TestCase):
    def test_auto_scale_shows_a_720p_layout_on_a_tv_in_game_mode(self):
        self.assertEqual([browser.scale("auto", True, h) for h in (800, 1080, 1200, 1440, 2160)], [None, 1.5, 1.75, 2.0, 3.0])
        self.assertIsNone(browser.scale("auto", False, 2160))
        self.assertEqual(browser.scale("1.25", False), 1.25)
        self.assertEqual(browser.scale("9", True), 4.0)
        self.assertIsNone(browser.scale("1", True))
        self.assertIsNone(browser.scale("big", True))

    def test_full_screen_apps_run_as_a_kiosk_with_tv_input(self):
        arguments = browser.flags(Path("/p"), "https://www.primevideo.com/", True, True, 1.5, "nonsteamapps-primevideo")
        self.assertEqual(arguments[:3], ["--user-data-dir=/p", "--class=nonsteamapps-primevideo", "--no-first-run"])
        for flag in ("--kiosk", "--enable-spatial-navigation", "--password-store=basic", "--ozone-platform=x11",
                     "--force-device-scale-factor=1.5", "--autoplay-policy=no-user-gesture-required"):
            self.assertIn(flag, arguments)
        self.assertEqual(arguments[-1], "https://www.primevideo.com/")

    def test_the_browser_opens_maximised_with_its_own_interface(self):
        arguments = browser.flags(Path("/p"), "", False, False, None, "nonsteamapps-helium")
        self.assertIn("--start-maximized", arguments)
        self.assertIn("--ozone-platform-hint=auto", arguments)
        self.assertNotIn("--kiosk", arguments)
        self.assertFalse(any(flag.startswith("--force-device-scale-factor") for flag in arguments))


if __name__ == "__main__":
    unittest.main()
