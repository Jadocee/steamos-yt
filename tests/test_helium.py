import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _fakes
from nonsteamapps import helium
from nonsteamapps.helium import HeliumError, Runtime


def gpg(home, *args, **kwargs):
    return subprocess.run(
        ["gpg", "--batch", "--homedir", str(home), "--pinentry-mode", "loopback", "--passphrase", "", *args],
        capture_output=True, text=True, check=True, **kwargs,
    ).stdout


@unittest.skipUnless(shutil.which("gpg") and shutil.which("gpgv"), "needs gpg and gpgv")
class SignatureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.keys = self.dir / "gnupg"
        self.keys.mkdir(mode=0o700)
        gpg(self.keys, "--quick-gen-key", "Test signer <signer@example.invalid>", "ed25519", "sign", "never")
        self.fingerprint = next(line.split(":")[9] for line in gpg(self.keys, "--with-colons", "--fingerprint").splitlines()
                                if line.startswith("fpr:"))
        (self.dir / "key.asc").write_text(gpg(self.keys, "--armor", "--export"))
        self.archive = _fakes.make_helium_archive(self.dir)
        gpg(self.keys, "--armor", "--detach-sign", "--output", f"{self.archive}.asc", str(self.archive))
        self.runtime = Runtime(self.dir / "helium", self.dir / "key.asc", fingerprint=self.fingerprint)

    def tearDown(self):
        subprocess.run(["gpgconf", "--homedir", str(self.keys), "--kill", "all"], capture_output=True, check=False)
        self.tmp.cleanup()

    def test_a_signed_archive_installs(self):
        self.assertTrue(self.runtime.verify(self.archive))
        self.assertEqual(self.runtime.install(self.archive), "0.0.0.1")
        self.assertEqual(self.runtime.current(), "0.0.0.1")
        self.assertTrue(os.access(self.runtime.executable, os.X_OK))

    def test_a_tampered_or_foreign_archive_is_refused(self):
        with open(self.archive, "ab") as handle:
            handle.write(b"tampered")
        self.assertFalse(self.runtime.verify(self.archive))
        with self.assertRaises(HeliumError):
            self.runtime.install(self.archive)
        self.assertIsNone(self.runtime.current())
        signed = self.dir / "signed"
        signed.mkdir()
        archive = _fakes.make_helium_archive(signed, "0.0.0.2")
        gpg(self.keys, "--armor", "--detach-sign", "--output", f"{archive}.asc", str(archive))
        stranger = Runtime(self.dir / "helium", self.dir / "key.asc", fingerprint="0" * 40)
        self.assertFalse(stranger.verify(archive))


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.runtime = Runtime(self.dir / "helium", self.dir / "missing.asc")
        self.quiet = mock.patch("nonsteamapps.helium.ui")
        self.quiet.start()

    def tearDown(self):
        self.quiet.stop()
        self.tmp.cleanup()

    def install(self, version):
        folder = self.dir / version
        folder.mkdir()
        return self.runtime.install(_fakes.make_helium_archive(folder, version), verify=False)

    def test_unsigned_archives_need_skip_verify(self):
        archive = _fakes.make_helium_archive(self.dir)
        with self.assertRaises(HeliumError):
            self.runtime.install(archive)
        self.assertEqual(self.runtime.install(archive, verify=False), "0.0.0.1")

    def test_keeps_two_versions_and_rolls_back(self):
        for version in ("1.0.0.1", "1.0.1.1", "1.1.0.1"):
            self.install(version)
        self.assertEqual(self.runtime.versions(), ["1.1.0.1", "1.0.1.1"])
        self.assertEqual(self.runtime.current(), "1.1.0.1")
        self.assertEqual(self.runtime.rollback(), "1.0.1.1")
        self.assertEqual(self.runtime.current(), "1.0.1.1")
        self.install("1.2.0.1")
        self.assertEqual(self.runtime.versions(), ["1.2.0.1", "1.1.0.1"])

    def test_rejects_archives_that_are_not_helium(self):
        bad = self.dir / "helium-2.0.0.1-x86_64_linux.tar.xz"
        (self.dir / "junk").mkdir()
        (self.dir / "junk" / "README").write_text("not a browser")
        subprocess.run(["tar", "-cJf", str(bad), "-C", str(self.dir), "junk"], check=True)
        with self.assertRaises(HeliumError):
            self.runtime.install(bad, verify=False)
        with self.assertRaises(HeliumError):
            self.runtime.install(self.dir / "browser.tar.xz", verify=False)
        self.assertEqual(self.runtime.versions(), [])

    def test_finds_the_latest_release_through_the_api_or_the_redirect(self):
        with mock.patch.object(helium, "_fetch_text", return_value='{"tag_name": "0.20.3.1"}'):
            self.assertEqual(self.runtime.latest(), "0.20.3.1")
        with mock.patch.object(helium, "_fetch_text", side_effect=OSError("403")), \
                mock.patch.object(helium, "_final_url", return_value="https://github.com/x/y/releases/tag/0.20.4.1"):
            self.assertEqual(self.runtime.latest(), "0.20.4.1")
        with mock.patch.object(helium, "_fetch_text", side_effect=OSError), \
                mock.patch.object(helium, "_final_url", side_effect=OSError):
            with self.assertRaises(HeliumError):
                self.runtime.latest()

    def test_update_installs_only_newer_releases(self):
        self.install("1.0.0.1")
        with mock.patch.object(Runtime, "latest", return_value="1.0.0.1"):
            self.assertIsNone(self.runtime.update())
        newer = self.dir / "dl"
        newer.mkdir()
        archive = _fakes.make_helium_archive(newer, "1.1.0.1")
        with mock.patch.object(Runtime, "latest", return_value="1.1.0.1"), \
                mock.patch.object(Runtime, "download", return_value=archive), \
                mock.patch.object(Runtime, "verify", return_value=True):
            self.assertEqual(self.runtime.update(), "1.1.0.1")
        self.assertEqual(self.runtime.current(), "1.1.0.1")

    def test_asset_names_follow_helium_releases(self):
        self.assertEqual(helium.asset_name("0.20.3.1", "x86_64"), "helium-0.20.3.1-x86_64_linux.tar.xz")
        self.assertTrue(helium.valid_version("0.20.3.1"))
        self.assertFalse(helium.valid_version("latest"))


if __name__ == "__main__":
    unittest.main()
