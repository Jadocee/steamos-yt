import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _fakes
from _fakes import ALPHA, BETA
from nonsteamapps import apps, cli, config, steam, vdf


class Exec(Exception):
    """Raised instead of replacing the test process."""


def fake_exec(file, argv):
    raise Exec(argv)


class CliTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.root = _fakes.make_steam(self.home)
        self.paths = _fakes.make_paths(self.home)
        self.fake = _fakes.FakeFlatpak(Path(self.tmp.name), self.preinstalled())
        self.flatpak = cli.Flatpak(self.fake.command)
        patches = [
            mock.patch.dict(os.environ, _fakes.environment(self.home, self.fake), clear=True),
            mock.patch("nonsteamapps.steamclient.running", return_value=False),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def preinstalled(self):
        return {}

    def run_cli(self, *argv):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            status = cli.main(list(argv), self.paths, self.flatpak)
        self.output, self.errors = output.getvalue(), errors.getvalue()
        return status

    def install(self, *names):
        self.assertEqual(self.run_cli("install", *names, "--yes", "--no-auto-update"), 0, self.errors)

    def entries(self, account):
        data = (steam.config_dir(self.root, account) / "shortcuts.vdf").read_bytes()
        return {entry.get("AppName"): entry for entry in vdf.loads_binary(data).get("shortcuts").values()}

    def launch(self, *argv):
        with mock.patch("nonsteamapps.cli.os.execvp", side_effect=fake_exec) as execvp, \
                mock.patch("nonsteamapps.cli._redirect") as redirect, \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(Exec):
                cli.main(["launch", *argv], self.paths, self.flatpak)
        return execvp.call_args[0][1], redirect


class InstallTests(CliTestCase):
    def test_first_install_adds_every_app_for_every_account(self):
        self.install()
        self.assertEqual(
            [call[-1] for call in self.fake.calls("install")],
            ["rocks.shy.VacuumTube", "im.riot.Riot", "org.jellyfin.JellyfinDesktop", "org.localsend.localsend_app"],
        )
        record = config.Record.load(self.paths.record)
        self.assertEqual(record.managed(), apps.ids())
        self.assertTrue(all(record.owns_flatpak(app_id) for app_id in apps.ids()))
        for account in (ALPHA, BETA):
            entries = self.entries(account)
            self.assertEqual(sorted(entries), ["Element", "Jellyfin", "LocalSend", "YouTube"])
            for app in apps.APPS:
                entry = entries[app.name]
                self.assertEqual(entry.get("Exe"), f'"{self.paths.app_link(app.id)}"')
                self.assertEqual(entry.get("LaunchOptions"), f"--steam-account {account}")
                self.assertEqual(entry.get("AllowOverlay"), 0)
                appid = steam.to_unsigned32(entry.get("appid"))
                grid = steam.config_dir(self.root, account) / "grid"
                self.assertTrue((grid / f"{appid}p.png").is_file())
                self.assertTrue((grid / f"{appid}_hero.jpg").is_file())
        for app_id in apps.ids():
            link = self.paths.app_link(app_id)
            self.assertEqual(link.resolve(), self.paths.launcher.resolve())
        self.assertTrue(self.paths.settings.is_file())

    def test_rerunning_without_names_repairs_only_the_apps_in_use(self):
        self.install("youtube")
        self.install()
        self.assertEqual([call[-1] for call in self.fake.calls("install")], ["rocks.shy.VacuumTube"])
        self.assertEqual(sorted(self.entries(ALPHA)), ["YouTube"])

    def test_unknown_app_is_rejected(self):
        self.assertEqual(self.run_cli("install", "netflix", "--yes"), 1)
        self.assertIn("unknown app 'netflix'", self.errors)

    def test_refuses_to_close_steam_in_game_mode(self):
        with mock.patch("nonsteamapps.steamclient.running", return_value=True), \
                mock.patch("nonsteamapps.steamclient.in_game_mode", return_value=True):
            self.assertEqual(self.run_cli("install", "youtube", "--yes", "--no-auto-update"), 1)
        self.assertIn("Switch to Desktop Mode", self.errors)
        self.assertFalse((steam.config_dir(self.root, ALPHA) / "shortcuts.vdf").exists())

    def test_update_timer_runs_the_launcher_weekly(self):
        bin_dir = Path(self.tmp.name) / "bin"
        bin_dir.mkdir()
        calls = Path(self.tmp.name) / "systemctl.log"
        (bin_dir / "systemctl").write_text(f'#!/bin/sh\necho "$*" >> "{calls}"\n')
        (bin_dir / "systemctl").chmod(0o755)
        with mock.patch.dict(os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}):
            self.assertEqual(self.run_cli("install", "youtube", "--yes"), 0, self.errors)
            service = (self.paths.systemd / "nonsteamapps-update.service").read_text()
            self.assertIn(f'ExecStart="{self.paths.launcher}" update --quiet', service)
            self.assertIn("--user enable --now nonsteamapps-update.timer", calls.read_text())
            self.assertEqual(self.run_cli("install", "--yes", "--no-auto-update"), 0, self.errors)
        self.assertFalse((self.paths.systemd / "nonsteamapps-update.timer").exists())


class ExistingFlatpakTests(CliTestCase):
    def preinstalled(self):
        return {"im.riot.Riot": {"version": "1.12.33", "installation": "system"}}

    def test_uses_an_installed_app_and_never_uninstalls_it(self):
        self.install("element")
        self.assertEqual(self.fake.calls("install"), [])
        self.assertIn("Element Desktop 1.12.33 is already installed (system installation)", self.errors)
        self.assertFalse(config.Record.load(self.paths.record).owns_flatpak("element"))
        self.assertEqual(self.run_cli("remove", "element", "--yes"), 0, self.errors)
        self.assertEqual(self.fake.calls("uninstall"), [])
        self.assertIn("stays installed", self.errors)
        self.assertEqual(self.entries(ALPHA), {})


class MigrationTests(CliTestCase):
    def test_takes_over_steamos_yt_and_its_shortcut(self):
        appid = _fakes.make_legacy(self.home, self.root, shared_sign_in=True)
        self.install("element")
        for account in (ALPHA, BETA):
            youtube = self.entries(account)["YouTube"]
            self.assertEqual(steam.to_unsigned32(youtube.get("appid")), appid)
            self.assertEqual(youtube.get("Exe"), f'"{self.paths.app_link("youtube")}"')
        self.assertEqual(config.Record.load(self.paths.record).managed(), ["youtube", "element"])
        self.assertFalse((self.home / ".local/share/steamos-yt").exists())
        self.assertFalse((self.home / ".config/steamos-yt").exists())
        self.assertEqual(config.read_settings(self.paths.settings)[cli.PER_ACCOUNT], "0")

    def test_keeps_steamos_yt_when_the_steam_library_is_left_alone(self):
        _fakes.make_legacy(self.home, self.root)
        self.assertEqual(self.run_cli("install", "--yes", "--no-auto-update", "--no-steam"), 0, self.errors)
        self.assertTrue((self.home / ".local/share/steamos-yt/bin/steamos-yt").exists())
        self.assertIn("Kept SteamOS YT", self.errors)


class LaunchTests(CliTestCase):
    def test_each_account_gets_its_own_vacuumtube_folder(self):
        self.install("youtube")
        argv, redirect = self.launch("youtube", "--steam-account", str(BETA), "--", "--debug-gpu")
        folder = self.home / f".var/app/rocks.shy.VacuumTube/config/VacuumTube-steam-{BETA}"
        self.assertEqual(argv, [self.fake.command, "run", "rocks.shy.VacuumTube", "--fullscreen", f"--portable={folder}", "--debug-gpu"])
        self.assertTrue(folder.is_dir())
        redirect.assert_called_once_with(self.paths.log("youtube"))

    def test_launch_outside_steam_uses_the_most_recent_account(self):
        argv, _ = self.launch("element")
        self.assertEqual(argv[-1], f"--profile=steam-{ALPHA}")

    def test_shared_data_when_separate_sign_ins_are_off(self):
        self.install("element")
        config.set_setting(self.paths.settings, cli.PER_ACCOUNT, "0")
        argv, _ = self.launch("element", "--steam-account", str(BETA))
        self.assertEqual(argv[3:], ["--password-store=basic", "--storage-mode=allow-plaintext"])
        argv, _ = self.launch("youtube", "--steam-account", str(BETA))
        self.assertEqual(argv[3:], ["--fullscreen"])
        self.assertTrue((self.home / ".var/app/rocks.shy.VacuumTube/config/VacuumTube/config.json").is_file())

    def test_jellyfin_profile_is_created_before_it_is_selected(self):
        argv, _ = self.launch("jellyfin", f"--steam-account={BETA}")
        self.assertEqual(self.fake.calls("run"), [["run", "org.jellyfin.JellyfinDesktop", "--create-profile", f"steam-{BETA}"]])
        self.assertEqual(argv[3:], ["--tv", "--fullscreen", f"--profile=steam-{BETA}"])
        self.launch("jellyfin", f"--steam-account={BETA}")
        self.assertEqual(len(self.fake.calls("run")), 1)

    def test_falls_back_to_shared_data_when_jellyfin_cannot_create_a_profile(self):
        with mock.patch.dict(os.environ, {"FAKE_FLATPAK_FAIL": "run"}):
            argv, _ = self.launch("jellyfin", "--steam-account", str(ALPHA))
        self.assertEqual(argv[3:], ["--tv", "--fullscreen"])

    def test_localsend_starts_with_its_own_settings_for_every_account(self):
        argv, redirect = self.launch("localsend", "--steam-account", str(BETA))
        self.assertEqual(argv, [self.fake.command, "run", "org.localsend.localsend_app"])
        self.assertFalse((self.home / ".var").exists())
        redirect.assert_called_once_with(self.paths.log("localsend"))

    def test_unknown_or_missing_app(self):
        self.assertEqual(self.run_cli("launch", "netflix"), 1)
        self.assertEqual(self.run_cli("launch", "--steam-account", "1"), 1)


class RemovalTests(CliTestCase):
    def test_remove_with_purge_deletes_only_per_account_data(self):
        self.install("youtube", "element")
        app_home = apps.by_id("youtube").home(self.home)
        ours, theirs = app_home / f"config/VacuumTube-steam-{ALPHA}", app_home / "config/VacuumTube"
        ours.mkdir(parents=True)
        theirs.mkdir(parents=True)
        self.assertEqual(self.run_cli("remove", "youtube", "--purge", "--yes"), 0, self.errors)
        self.assertFalse(ours.exists())
        self.assertTrue(theirs.is_dir())
        self.assertEqual(sorted(self.entries(BETA)), ["Element"])
        self.assertFalse(self.paths.app_link("youtube").is_symlink())
        self.assertNotIn("rocks.shy.VacuumTube", self.fake.apps())
        self.assertEqual(self.fake.calls("uninstall")[-1], ["uninstall", "--user", "--unused", "--noninteractive", "-y"])
        self.assertEqual(config.Record.load(self.paths.record).managed(), ["element"])

    def test_purge_needs_a_clear_yes(self):
        self.install("youtube")
        with mock.patch("nonsteamapps.ui.confirm", return_value=False):
            self.assertEqual(self.run_cli("remove", "youtube", "--purge"), 1)
        self.assertEqual(sorted(self.entries(ALPHA)), ["YouTube"])

    def test_keep_app_only_removes_the_shortcut(self):
        self.install("jellyfin")
        self.assertEqual(self.run_cli("remove", "jellyfin", "--keep-app", "--yes"), 0, self.errors)
        self.assertIn("org.jellyfin.JellyfinDesktop", self.fake.apps())
        self.assertEqual(self.entries(ALPHA), {})

    def test_uninstall_removes_everything_but_settings_and_sign_ins(self):
        self.install()
        data = apps.by_id("element").home(self.home) / f"config/Element-steam-{ALPHA}"
        data.mkdir(parents=True)
        self.assertEqual(self.run_cli("uninstall", "--yes"), 0, self.errors)
        self.assertFalse(self.paths.program.exists())
        self.assertFalse(self.paths.state.exists())
        self.assertTrue(self.paths.settings.is_file())
        self.assertTrue(data.is_dir())
        self.assertEqual(self.fake.apps(), {})
        self.assertEqual(self.entries(ALPHA), {})

    def test_uninstall_refuses_an_unexpected_folder(self):
        (self.paths.program / "lib" / "nonsteamapps" / "__init__.py").unlink()
        self.assertEqual(self.run_cli("uninstall", "--yes"), 1)
        self.assertTrue(self.paths.program.is_dir())


class InformationTests(CliTestCase):
    def test_update_only_touches_apps_it_installed(self):
        self.fake.state.write_text('{"apps": {"im.riot.Riot": {"version": "1", "installation": "user"}}}')
        self.install("youtube", "element")
        self.assertEqual(self.run_cli("update", "--quiet"), 0, self.errors)
        self.assertEqual(self.fake.calls("update"), [["update", "--user", "--noninteractive", "-y", "rocks.shy.VacuumTube"]])

    def test_list_status_and_doctor(self):
        self.install("youtube")
        self.assertEqual(self.run_cli("list"), 0)
        self.assertRegex(self.output, r"youtube\s+in use\s+VacuumTube 1\.0\.0 \(user installation, installed by NonSteamApps\)")
        self.assertRegex(self.output, r"element\s+available\s+not installed")
        self.assertEqual(self.run_cli("steam", "status"), 0)
        self.assertIn(f'Steam account P{BETA} ({BETA}): present "YouTube"', self.output)
        self.assertEqual(self.run_cli("doctor"), 0)
        self.assertIn("youtube", self.output)
        self.assertIn('in the library as "YouTube"', self.output)


if __name__ == "__main__":
    unittest.main()
