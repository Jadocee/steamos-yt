import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _fakes
from nonsteamapps.flatpak import Flatpak, FlatpakError, Installed


class FlatpakTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        installed = {
            "rocks.shy.VacuumTube": {"version": "2.0.1", "installation": "user"},
            "im.riot.Riot": {"version": "", "installation": "system"},
        }
        self.fake = _fakes.FakeFlatpak(Path(self.tmp.name), installed)
        self.env = mock.patch.dict(os.environ, self.fake.env)
        self.env.start()
        self.flatpak = Flatpak(self.fake.command)

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_lists_installed_apps_with_their_installation(self):
        self.assertTrue(self.flatpak.available())
        self.assertEqual(
            self.flatpak.installed(),
            {"rocks.shy.VacuumTube": Installed("2.0.1", "user"), "im.riot.Riot": Installed("", "system")},
        )
        self.assertEqual(self.flatpak.installation("im.riot.Riot"), "system")
        self.assertIsNone(self.flatpak.installation("org.jellyfin.JellyfinDesktop"))

    def test_installs_into_the_user_installation_from_flathub(self):
        self.flatpak.install("org.jellyfin.JellyfinDesktop")
        self.assertEqual(
            self.fake.calls()[-2:],
            [
                ["remote-add", "--user", "--if-not-exists", "flathub", "https://dl.flathub.org/repo/flathub.flatpakrepo"],
                ["install", "--user", "--noninteractive", "-y", "flathub", "org.jellyfin.JellyfinDesktop"],
            ],
        )
        self.assertEqual(self.flatpak.installation("org.jellyfin.JellyfinDesktop"), "user")

    def test_failures_raise_and_listing_failures_mean_nothing_installed(self):
        with mock.patch.dict(os.environ, {"FAKE_FLATPAK_FAIL": "install"}):
            with self.assertRaises(FlatpakError):
                self.flatpak.install("org.jellyfin.JellyfinDesktop")
        with mock.patch.dict(os.environ, {"FAKE_FLATPAK_FAIL": "list"}):
            self.assertEqual(self.flatpak.installed(), {})

    def test_update_uninstall_and_run(self):
        self.flatpak.update([])
        self.assertEqual(self.fake.calls("update"), [])
        self.flatpak.update(["rocks.shy.VacuumTube"], quiet=True)
        self.flatpak.uninstall("rocks.shy.VacuumTube")
        self.flatpak.remove_unused()
        self.assertEqual(
            self.fake.calls()[-3:],
            [
                ["update", "--user", "--noninteractive", "-y", "rocks.shy.VacuumTube"],
                ["uninstall", "--user", "--noninteractive", "-y", "rocks.shy.VacuumTube"],
                ["uninstall", "--user", "--unused", "--noninteractive", "-y"],
            ],
        )
        self.assertEqual(self.flatpak.run_args("im.riot.Riot", ["--a"]), [self.fake.command, "run", "im.riot.Riot", "--a"])
        self.assertEqual(
            self.flatpak.run_args("org.signal.Signal", ["A=1", "signal-desktop"], ["--command=env"]),
            [self.fake.command, "run", "--command=env", "org.signal.Signal", "A=1", "signal-desktop"],
        )
        self.assertEqual(self.flatpak.run_quietly("im.riot.Riot", ["--b"]), 0)
        self.assertEqual(self.fake.calls()[-1], ["run", "im.riot.Riot", "--b"])

    def test_missing_command_is_reported(self):
        missing = Flatpak("/nonexistent/flatpak")
        self.assertFalse(missing.available())
        self.assertEqual(missing.installed(), {})
        with self.assertRaises(FlatpakError):
            missing.install("im.riot.Riot")


if __name__ == "__main__":
    unittest.main()
