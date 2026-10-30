import tempfile
import unittest
from pathlib import Path

import _paths  # noqa: F401
from nonsteamapps import config


class SettingsTests(unittest.TestCase):
    def test_parses_values_and_ignores_noise(self):
        text = "# comment\nPROFILE_PER_STEAM_ACCOUNT=0\n  QUOTED = \"a b\" # note\nlower=1\nnot a setting\nEMPTY=\n"
        self.assertEqual(
            config.parse_settings(text),
            {"PROFILE_PER_STEAM_ACCOUNT": "0", "QUOTED": "a b", "EMPTY": ""},
        )

    def test_enabled_understands_common_spellings(self):
        self.assertTrue(all(config.enabled(value) for value in ("1", "yes", "On", "TRUE")))
        self.assertFalse(any(config.enabled(value) for value in ("0", "no", "off", "maybe")))
        self.assertTrue(config.enabled(None, default=True))
        self.assertTrue(config.enabled("  ", default=True))

    def test_paths_follow_xdg_variables(self):
        environ = {"HOME": "/home/deck", "XDG_CONFIG_HOME": "/cfg", "XDG_STATE_HOME": "relative"}
        paths = config.Paths.detect(Path("/opt/nsa"), environ)
        self.assertEqual(paths.settings, Path("/cfg/nonsteamapps/nonsteamapps.conf"))
        self.assertEqual(paths.record, Path("/home/deck/.local/state/nonsteamapps/apps.json"))
        self.assertEqual(paths.systemd, Path("/cfg/systemd/user"))
        self.assertEqual(paths.app_link("youtube"), Path("/opt/nsa/apps/youtube"))
        self.assertEqual(paths.launcher, Path("/opt/nsa/bin/nonsteamapps"))


class DefaultsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.shipped = self.dir / "shipped.conf"
        self.target = self.dir / "cfg" / "nonsteamapps.conf"
        self.shipped.write_text("A=1\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_new_defaults_replace_an_untouched_file_but_never_an_edited_one(self):
        self.assertEqual(config.install_defaults(self.shipped, self.target), "")
        self.shipped.write_text("A=2\n")
        self.assertIn("Updated", config.install_defaults(self.shipped, self.target))
        self.assertEqual(self.target.read_text(), "A=2\n")
        self.target.write_text("A=9\n")
        self.shipped.write_text("A=3\n")
        self.assertIn("Kept your", config.install_defaults(self.shipped, self.target))
        self.assertEqual(self.target.read_text(), "A=9\n")
        self.assertEqual(self.target.with_name("nonsteamapps.conf.default").read_text(), "A=3\n")

    def test_set_setting_replaces_or_appends(self):
        self.target.parent.mkdir()
        self.target.write_text("# c\nA=1\n")
        config.set_setting(self.target, "A", "0")
        config.set_setting(self.target, "B", "x")
        self.assertEqual(self.target.read_text(), "# c\nA=0\nB=x\n")


class RecordTests(unittest.TestCase):
    def test_round_trip_and_ownership_is_sticky(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state" / "apps.json"
            record = config.Record.load(path)
            self.assertEqual(record.managed(), [])
            record.add("youtube", installed_flatpak=True)
            record.add("youtube", installed_flatpak=False)
            record.add("element", installed_flatpak=False)
            record.save()
            loaded = config.Record.load(path)
            self.assertEqual(loaded.managed(), ["youtube", "element"])
            self.assertTrue(loaded.owns_flatpak("youtube"))
            self.assertFalse(loaded.owns_flatpak("element"))
            loaded.discard("youtube")
            self.assertEqual(loaded.managed(), ["element"])

    def test_corrupt_record_starts_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "apps.json"
            path.write_text("{not json")
            self.assertEqual(config.Record.load(path).managed(), [])


if __name__ == "__main__":
    unittest.main()
