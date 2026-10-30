import os
import unittest
from types import SimpleNamespace
from unittest import mock

import _paths  # noqa: F401
from nonsteamapps import display


class ScaleTests(unittest.TestCase):
    def test_auto_scale_shows_a_720p_layout_on_a_tv_in_game_mode(self):
        self.assertEqual([display.scale("auto", True, h) for h in (800, 1080, 1200, 1440, 2160)], [None, 1.5, 1.75, 2.0, 3.0])
        self.assertIsNone(display.scale("auto", False, 2160))
        self.assertEqual(display.scale("1.25", False), 1.25)
        self.assertEqual(display.scale("9", True), 4.0)
        self.assertIsNone(display.scale("1", True))
        self.assertIsNone(display.scale("big", True))

    def test_the_screen_height_comes_from_xrandr(self):
        output = "Screen 0: minimum 16 x 16, current 3840 x 2160, maximum 32767 x 32767\n"
        with mock.patch.dict(os.environ, {"DISPLAY": ":0"}), \
                mock.patch("nonsteamapps.display.shutil.which", return_value="/usr/bin/xrandr"), \
                mock.patch("nonsteamapps.display.subprocess.run", return_value=SimpleNamespace(stdout=output)):
            self.assertEqual(display.screen_height(), 2160)
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(display.screen_height())


if __name__ == "__main__":
    unittest.main()
