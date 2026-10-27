import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import _paths  # noqa: F401
from steamos_yt import profile


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.profile = Path(self.tmp.name) / "profile"
        self.prefs = self.profile / "Default" / "Preferences"

    def tearDown(self):
        self.tmp.cleanup()

    def read(self):
        return json.loads(self.prefs.read_text())

    def test_seed_creates_kiosk_defaults(self):
        profile.seed_profile(self.profile)
        prefs = self.read()
        self.assertTrue(prefs["helium"]["completed_onboarding"])
        self.assertTrue(prefs["helium"]["services"]["user_consented"])
        self.assertFalse(prefs["translate"]["enabled"])
        self.assertEqual(prefs["profile"]["default_content_setting_values"]["notifications"], 2)

    def test_seed_merges_without_losing_user_state(self):
        self.prefs.parent.mkdir(parents=True)
        self.prefs.write_text(json.dumps({
            "helium": {"services": {"origin_override": "https://example.org"}},
            "profile": {"name": "Person", "exit_type": "Crashed"},
            "extensions": {"settings": {"abc": {"state": 1}}},
        }))
        profile.seed_profile(self.profile, services=False)
        prefs = self.read()
        self.assertEqual(prefs["helium"]["services"]["origin_override"], "https://example.org")
        self.assertFalse(prefs["helium"]["services"]["user_consented"])
        self.assertEqual(prefs["profile"]["name"], "Person")
        self.assertEqual(prefs["profile"]["exit_type"], "Normal")
        self.assertIn("abc", prefs["extensions"]["settings"])

    def test_corrupt_preferences_are_backed_up(self):
        self.prefs.parent.mkdir(parents=True)
        self.prefs.write_text("{not json")
        profile.seed_profile(self.profile)
        self.assertEqual((self.prefs.parent / "Preferences.corrupt").read_text(), "{not json")
        self.assertIn("helium", self.read())

    def test_mark_clean_exit(self):
        self.assertFalse(profile.mark_clean_exit(self.profile))
        self.prefs.parent.mkdir(parents=True)
        self.prefs.write_text(json.dumps({"profile": {"exit_type": "Crashed", "exited_cleanly": False}}))
        self.assertTrue(profile.mark_clean_exit(self.profile))
        self.assertEqual(self.read()["profile"], {"exit_type": "Normal", "exited_cleanly": True})
        self.assertFalse(profile.mark_clean_exit(self.profile))



class AccountProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.shared = self.home / "profile"

    def tearDown(self):
        self.tmp.cleanup()

    def account(self, account):
        return self.home / "profiles" / str(account)

    def make_shared(self):
        (self.shared / "Default").mkdir(parents=True)
        (self.shared / "Default" / "Cookies").write_text("signed in")

    def fake_browser(self):
        sleep = shutil.which("sleep")
        if not sleep:
            self.skipTest("sleep is not available")
        binary = self.home / "bin" / "helium"
        binary.parent.mkdir()
        shutil.copy(sleep, binary)
        try:
            process = subprocess.Popen([str(binary), "30"])
        except OSError as exc:
            self.skipTest(f"cannot run a copied binary here: {exc}")
        self.addCleanup(process.wait)
        self.addCleanup(process.kill)
        return process

    def test_profile_paths(self):
        self.assertEqual(profile.profile_dir(self.home, 5), self.account(5))
        self.assertEqual(profile.profile_dir(self.home, 5, per_account=False), self.shared)
        self.assertEqual(profile.profile_dir(self.home, None), self.shared)

    def test_first_account_inherits_the_shared_profile(self):
        self.make_shared()
        self.assertEqual(profile.resolve_profile(self.home, 5), self.account(5))
        self.assertEqual((self.account(5) / "Default" / "Cookies").read_text(), "signed in")
        self.assertFalse(self.shared.exists())
        self.assertEqual(profile.resolve_profile(self.home, 6), self.account(6))
        self.assertFalse(self.account(6).exists())

    def test_shared_profile_stays_once_accounts_have_profiles(self):
        self.account(6).mkdir(parents=True)
        self.make_shared()
        self.assertFalse(profile.adoption_pending(self.home))
        self.assertFalse(profile.adopt_shared_profile(self.home, 5))
        self.assertEqual(profile.resolve_profile(self.home, 5), self.account(5))
        self.assertTrue(self.shared.exists())

    def test_shared_profile_is_used_without_an_account_or_when_turned_off(self):
        self.make_shared()
        self.assertEqual(profile.resolve_profile(self.home, None), self.shared)
        self.assertEqual(profile.resolve_profile(self.home, 5, per_account=False), self.shared)
        self.assertTrue(profile.adoption_pending(self.home))

    def test_open_shared_profile_is_handed_over_on_a_later_launch(self):
        self.make_shared()
        browser = self.fake_browser()
        os.symlink(f"steamdeck-{browser.pid}", self.shared / "SingletonLock")
        self.assertTrue(profile.in_use(self.shared))
        self.assertEqual(profile.resolve_profile(self.home, 5), self.shared)
        browser.kill()
        browser.wait()
        self.assertFalse(profile.in_use(self.shared))
        self.assertEqual(profile.resolve_profile(self.home, 5), self.account(5))

    def test_lock_naming_an_unrelated_process_is_stale(self):
        self.make_shared()
        os.symlink(f"steamdeck-{os.getpid()}", self.shared / "SingletonLock")
        self.assertFalse(profile.in_use(self.shared))
        self.assertTrue(profile.adopt_shared_profile(self.home, 5))

    def test_all_profiles_lists_shared_then_accounts_in_order(self):
        self.make_shared()
        for name in ("20", "3", "notes"):
            self.account(name).mkdir(parents=True)
        self.assertEqual(profile.all_profiles(self.home), [self.shared, self.account(3), self.account(20)])

    def test_prepare_seeds_new_profiles_and_tidies_existing_ones(self):
        directory = self.account(5)
        profile.prepare_profile(directory, services=False)
        path = profile.preferences_path(directory)
        prefs = json.loads(path.read_text())
        self.assertFalse(prefs["helium"]["services"]["user_consented"])
        prefs["profile"]["exit_type"] = "Crashed"
        prefs["helium"]["services"]["user_consented"] = True
        path.write_text(json.dumps(prefs))
        profile.prepare_profile(directory, services=False)
        prefs = json.loads(path.read_text())
        self.assertEqual(prefs["profile"]["exit_type"], "Normal")
        self.assertTrue(prefs["helium"]["services"]["user_consented"])


if __name__ == "__main__":
    unittest.main()
