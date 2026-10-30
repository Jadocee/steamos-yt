import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _fakes
from nonsteamapps import legacy


class LegacyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.legacy = legacy.Legacy.detect({"HOME": str(self.home)})

    def tearDown(self):
        self.tmp.cleanup()

    def test_nothing_to_do_without_steamos_yt(self):
        self.assertFalse(self.legacy.present())
        self.assertIsNone(self.legacy.separate_profiles())

    def test_finds_every_leftover_and_the_old_sign_in_choice(self):
        root = _fakes.make_steam(self.home)
        _fakes.make_legacy(self.home, root, shared_sign_in=True)
        self.legacy.desktop_file.parent.mkdir(parents=True)
        self.legacy.desktop_file.write_text("[Desktop Entry]\n")
        self.legacy.units[1].parent.mkdir(parents=True)
        self.legacy.units[1].write_text("[Timer]\n")
        self.legacy.cache.mkdir(parents=True)
        self.assertEqual(
            self.legacy.leftovers(),
            [self.legacy.program, self.legacy.config, self.legacy.cache, self.legacy.desktop_file, self.legacy.units[1]],
        )
        self.assertIs(self.legacy.separate_profiles(), False)
        with mock.patch("nonsteamapps.legacy.shutil.which", return_value=None):
            removed = self.legacy.remove()
        self.assertEqual(len(removed), 5)
        self.assertFalse(any(path.exists() for path in removed))
        self.assertFalse(self.legacy.present())

    def test_never_deletes_an_unrecognised_folder_of_the_same_name(self):
        (self.legacy.program / "notes").mkdir(parents=True)
        self.assertFalse(self.legacy.present())
        with mock.patch("nonsteamapps.legacy.shutil.which", return_value=None):
            self.assertEqual(self.legacy.remove(), [])
        self.assertTrue((self.legacy.program / "notes").is_dir())


if __name__ == "__main__":
    unittest.main()
