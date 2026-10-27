import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

import _paths  # noqa: F401
from steamos_yt import cli, profile
from test_steam import ACCOUNT, OTHER, make_steam

URL = "https://www.youtube.com/tv"


def run_cli(*args):
    out, err = StringIO(), StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        status = cli.main([str(arg) for arg in args])
    return status, out.getvalue(), err.getvalue()


class AccountCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.root = make_steam(self.home)
        self.app = self.home / "app"
        self.extension = self.home / "extension"
        self.extension.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def account(self, account):
        return self.app / "profiles" / str(account)

    def prepare(self, *extra, steam_root=None):
        status, out, err = run_cli(
            "launch-prepare", "--extension", self.extension, "--url", URL, "--app-home", self.app,
            "--steam-root", steam_root or self.root, *extra,
        )
        self.assertEqual((status, err), (0, ""))
        return Path(out.splitlines()[2])

    def consented(self, directory):
        prefs = json.loads(profile.preferences_path(directory).read_text())
        return prefs["helium"]["services"]["user_consented"]

    def test_each_steam_account_gets_its_own_profile(self):
        self.assertEqual(self.prepare(), self.account(ACCOUNT))
        self.assertEqual(self.prepare("--steam-account", OTHER), self.account(OTHER))
        self.assertTrue(profile.preferences_path(self.account(ACCOUNT)).exists())
        self.assertTrue(profile.preferences_path(self.account(OTHER)).exists())
        self.assertFalse((self.app / "profile").exists())

    def test_shared_profile_when_turned_off_or_steam_is_missing(self):
        self.assertEqual(self.prepare("--steam-account", OTHER, "--per-account", "0"), self.app / "profile")
        self.assertEqual(self.prepare(steam_root=self.home / "missing"), self.app / "profile")
        self.assertEqual(self.prepare("--steam-account", OTHER, steam_root=self.home / "missing"), self.account(OTHER))

    def test_upgrade_hands_the_shared_profile_to_the_launching_account(self):
        (self.app / "profile" / "Default").mkdir(parents=True)
        (self.app / "profile" / "Default" / "Cookies").write_text("signed in")
        self.assertEqual(self.prepare("--steam-account", OTHER), self.account(OTHER))
        self.assertEqual((self.account(OTHER) / "Default" / "Cookies").read_text(), "signed in")
        self.assertEqual(self.prepare(), self.account(ACCOUNT))
        self.assertFalse((self.account(ACCOUNT) / "Default" / "Cookies").exists())

    def test_new_profiles_follow_the_helium_services_choice(self):
        self.assertFalse(self.consented(self.prepare("--helium-services", "0")))
        self.assertTrue(self.consented(self.prepare("--steam-account", OTHER)))

    def test_install_adopts_for_the_most_recent_account_and_seeds_every_profile(self):
        (self.app / "profile" / "Default").mkdir(parents=True)
        status, out, _ = run_cli("profile-adopt", "--app-home", self.app, "--steam-root", self.root)
        self.assertEqual((status, out.strip()), (0, f"Steam account u{ACCOUNT} ({ACCOUNT})"))
        status, out, _ = run_cli("profile-adopt", "--app-home", self.app, "--steam-root", self.root)
        self.assertEqual((status, out), (0, ""))
        self.account(OTHER).mkdir(parents=True)
        status, out, _ = run_cli("profile-seed-all", "--app-home", self.app, "--no-services")
        self.assertEqual(out.splitlines(), [str(self.account(ACCOUNT)), str(self.account(OTHER))])
        self.assertFalse(self.consented(self.account(ACCOUNT)))
        self.assertFalse(self.consented(self.account(OTHER)))

    def test_steam_accounts_lists_names_and_the_default_account(self):
        status, out, _ = run_cli("steam-accounts", "--steam-root", self.root)
        self.assertEqual((status, out.splitlines()), (0, [f"{ACCOUNT}\tu{ACCOUNT}\t1", f"{OTHER}\tu{OTHER}\t0"]))

    def test_reports_name_accounts(self):
        artwork = self.home / "artwork"
        artwork.mkdir()
        status, out, _ = run_cli(
            "shortcut-add", "--exe", "/opt/steamos-yt/bin/steamos-yt", "--start-dir", "/opt/steamos-yt",
            "--name", "YouTube", "--artwork-dir", artwork, "--user", "all", "--steam-root", self.root,
            "--launch-options=--steam-account {account}",
        )
        self.assertEqual(status, 0)
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith(f'Steam account u{ACCOUNT} ({ACCOUNT}): added "YouTube"'), lines)
        self.assertTrue(lines[1].startswith(f'Steam account u{OTHER} ({OTHER}): added "YouTube"'), lines)


if __name__ == "__main__":
    unittest.main()
