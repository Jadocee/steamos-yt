import unittest

import _paths  # noqa: F401
from nonsteamapps import steamclient

OVERLAY_32 = "/home/deck/.local/share/Steam/ubuntu12_32/gameoverlayrenderer.so"
OVERLAY_64 = "/home/deck/.local/share/Steam/ubuntu12_64/gameoverlayrenderer.so"
RUNTIME = "/home/deck/.local/share/Steam/ubuntu12_32/steam-runtime/usr/lib/x86_64-linux-gnu"


class SteamEnvironmentTests(unittest.TestCase):
    def test_steams_overlay_and_runtime_paths_are_removed(self):
        environ = {
            "LD_PRELOAD": f"{OVERLAY_32}:{OVERLAY_64} /usr/lib/mangohud/libMangoHud.so",
            "LD_LIBRARY_PATH": RUNTIME,
            "SYSTEM_LD_LIBRARY_PATH": "",
            "PATH": "/home/deck/.local/share/Steam/ubuntu12_32/steam-runtime/usr/bin:/usr/bin",
            "SYSTEM_PATH": "/usr/local/bin:/usr/bin",
        }
        self.assertTrue(steamclient.leave_steam_environment(environ))
        self.assertEqual(
            environ,
            {
                "LD_PRELOAD": "/usr/lib/mangohud/libMangoHud.so",
                "SYSTEM_LD_LIBRARY_PATH": "",
                "PATH": "/usr/local/bin:/usr/bin",
                "SYSTEM_PATH": "/usr/local/bin:/usr/bin",
            },
        )

    def test_the_systems_own_library_path_comes_back(self):
        environ = {"LD_PRELOAD": OVERLAY_64, "LD_LIBRARY_PATH": f"{RUNTIME}:/opt/lib", "SYSTEM_LD_LIBRARY_PATH": "/opt/lib"}
        self.assertTrue(steamclient.leave_steam_environment(environ))
        self.assertEqual(environ, {"LD_LIBRARY_PATH": "/opt/lib", "SYSTEM_LD_LIBRARY_PATH": "/opt/lib"})

    def test_outside_steam_nothing_changes(self):
        environ = {"LD_LIBRARY_PATH": "/opt/lib", "PATH": "/usr/bin"}
        self.assertFalse(steamclient.leave_steam_environment(environ))
        self.assertEqual(environ, {"LD_LIBRARY_PATH": "/opt/lib", "PATH": "/usr/bin"})


if __name__ == "__main__":
    unittest.main()
