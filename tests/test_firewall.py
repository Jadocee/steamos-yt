import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _fakes
from nonsteamapps import firewall


class FirewallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fake = _fakes.FakeFirewall(Path(self.tmp.name), running=True)
        patch = mock.patch.dict(os.environ, self.fake.env)
        patch.start()
        self.addCleanup(patch.stop)
        self.wall = self.fake.firewall()

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_missing_or_stopped_firewall_is_not_running(self):
        self.assertTrue(self.wall.running())
        self.assertFalse(firewall.Firewall("/nonexistent/firewall-cmd").running())
        self.fake.set(running=False)
        self.assertFalse(self.wall.running())

    def test_zones_in_use_or_else_the_default_zone(self):
        self.fake.set(active=("home", "public"))
        self.assertEqual(self.wall.zones(), ["home", "public"])
        self.fake.set(active=())
        self.assertEqual(self.wall.zones(), ["public"])

    def test_opens_and_closes_ports_for_now_and_permanently(self):
        ports = ("53317/tcp", "53317/udp")
        self.assertEqual(self.wall.closed(ports), {"public": ["53317/tcp", "53317/udp"]})
        self.wall.change("add", {"public": ["53317/tcp"]})
        self.assertEqual(self.wall.closed(ports), {"public": ["53317/udp"]})
        self.assertEqual((self.fake.ports(), self.fake.ports(permanent=False)), (["53317/tcp"], ["53317/tcp"]))
        self.wall.change("remove", {"public": ["53317/tcp"]})
        self.assertEqual((self.fake.ports(), self.fake.ports(permanent=False)), ([], []))

    def test_a_failure_lists_the_commands_still_to_run(self):
        with mock.patch.dict(os.environ, {"FAKE_SUDO_FAIL": "1"}):
            with self.assertRaises(firewall.FirewallError) as raised:
                self.wall.change("add", {"public": ["53317/tcp"]})
        self.assertEqual(str(raised.exception), "sudo: a password is required")
        self.assertEqual(
            raised.exception.commands,
            ["sudo firewall-cmd --permanent --zone=public --add-port=53317/tcp", "sudo firewall-cmd --zone=public --add-port=53317/tcp"],
        )
        self.assertEqual(json.loads(self.fake.state.read_text())["permanent"], {})


if __name__ == "__main__":
    unittest.main()
