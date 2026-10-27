import json
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


if __name__ == "__main__":
    unittest.main()
