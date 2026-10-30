import tempfile
import unittest
from pathlib import Path

import _paths  # noqa: F401
from nonsteamapps import controllers, vdf

ACCOUNT = 111


def template(kind, title, english=True):
    title_part = f'"localization" {{ "english" {{ "title" "{title}" }} }}' if english else f'"title" "{title}"'
    return f'"controller_mappings"\n{{\n "version" "3"\n "controller_type" "{kind}"\n {title_part}\n}}\n'


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        templates = controllers.templates_dir(self.root)
        templates.mkdir(parents=True)
        (templates / "controller_neptune_webbrowser.vdf").write_text(template("controller_neptune", "Web Browser"))
        (templates / "controller_xboxone_webbrowser.vdf").write_text(template("controller_xboxone", "Web Browser", english=False))
        (templates / "controller_neptune_gamepad.vdf").write_text(template("controller_neptune", "Gamepad"))
        (templates / "broken.vdf").write_text('"controller_mappings" {')

    def tearDown(self):
        self.tmp.cleanup()

    def configset(self, kind):
        path = controllers.config_dir(self.root, ACCOUNT) / f"configset_{kind}.vdf"
        return vdf.loads_text(path.read_text()).get("controller_config")

    def test_finds_valves_layout_by_title_for_each_controller(self):
        self.assertEqual(
            controllers.find_templates(self.root, "web browser"),
            {"controller_neptune": "controller_neptune_webbrowser.vdf", "controller_xboxone": "controller_xboxone_webbrowser.vdf"},
        )
        self.assertEqual(controllers.find_templates(self.root / "nowhere", "Web Browser"), {})

    def test_assigns_under_steams_name_for_the_shortcut_and_releases_only_its_own(self):
        layouts = controllers.find_templates(self.root, "Web Browser")
        self.assertEqual(controllers.assign(self.root, ACCOUNT, "Prime Video", layouts), ["controller_neptune", "controller_xboxone"])
        self.assertEqual(controllers.assign(self.root, ACCOUNT, "Prime Video", layouts), ["controller_neptune", "controller_xboxone"])
        entry = self.configset("controller_neptune").get("prime video")
        self.assertEqual(entry.get("template"), "controller_neptune_webbrowser.vdf")
        self.assertEqual(controllers.entry_name('H.B/O: Max?'), "hbo max")
        self.assertEqual(sorted(controllers.release(self.root, ACCOUNT, "Prime Video")), ["controller_neptune", "controller_xboxone"])
        self.assertIsNone(self.configset("controller_neptune").get("prime video"))

    def test_never_replaces_a_layout_the_user_picked(self):
        path = controllers.config_dir(self.root, ACCOUNT) / "configset_controller_neptune.vdf"
        path.parent.mkdir(parents=True)
        path.write_text('"controller_config"\n{\n\t"helium"\n\t{\n\t\t"workshop"\t\t"12345"\n\t}\n\t"other game"\n\t{\n\t\t"template"\t\t"x.vdf"\n\t}\n}\n')
        layouts = controllers.find_templates(self.root, "Web Browser")
        self.assertEqual(controllers.assign(self.root, ACCOUNT, "Helium", layouts), ["controller_xboxone"])
        section = self.configset("controller_neptune")
        self.assertEqual(section.get("helium").get("workshop"), "12345")
        self.assertEqual(section.get("other game").get("template"), "x.vdf")
        self.assertEqual(controllers.release(self.root, ACCOUNT, "Helium"), ["controller_xboxone"])
        self.assertEqual(self.configset("controller_neptune").get("helium").get("workshop"), "12345")


if __name__ == "__main__":
    unittest.main()
