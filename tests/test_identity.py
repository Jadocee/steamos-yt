import json
import re
import tempfile
import unittest
from pathlib import Path

import _paths  # noqa: F401
from steamos_yt import cli, identity


class IdentityTests(unittest.TestCase):
    def test_cobalt_user_agent_format(self):
        ident = identity.cobalt_identity(app_version="1.2.3", machine="x86_64", year=2026)
        self.assertEqual(
            ident.user_agent,
            "Mozilla/5.0 (X11; Linux x86_64) Cobalt/27.lts.3.1040976-gold (unlike Gecko) "
            "v8/13.8.258.54-jit gles Starboard/18, SteamOSYT_DESKTOP_x8664_2026/1.2.3 "
            "(SteamOSYT, Linux) io.github.jadocee.SteamOSYT/1.2.3",
        )
        self.assertEqual((ident.major_version, ident.full_version), ("27", "27.lts.3"))
        self.assertEqual((ident.platform, ident.architecture, ident.bitness), ("Starboard", "x86", "64"))

    def test_arm_identity(self):
        ident = identity.cobalt_identity(machine="aarch64", year=2026)
        self.assertIn("(X11; Linux aarch64)", ident.user_agent)
        self.assertIn("_DESKTOP_arm64_2026/", ident.user_agent)
        self.assertEqual(ident.architecture, "arm")

    def test_client_hints_match_identity(self):
        hints = identity.cobalt_identity(machine="x86_64").client_hints()
        self.assertEqual(hints["sec-ch-ua"], '"SteamOSYT";v="27"')
        self.assertEqual(hints["sec-ch-ua-platform"], '"Starboard"')
        self.assertEqual(hints["sec-ch-ua-mobile"], "?0")
        self.assertEqual(hints["sec-ch-ua-full-version-list"], '"SteamOSYT";v="27.lts.3"')

    def test_dnr_rules(self):
        self.assertEqual(identity.dnr_rules(None), [])
        [rule] = identity.dnr_rules(identity.cobalt_identity(machine="x86_64"))
        self.assertEqual(rule["action"]["type"], "modifyHeaders")
        self.assertIn("main_frame", rule["condition"]["resourceTypes"])
        self.assertIn("youtube.com", rule["condition"]["requestDomains"])
        headers = {item["header"]: item for item in rule["action"]["requestHeaders"]}
        self.assertEqual(headers["sec-ch-ua-platform"]["operation"], "set")

    def test_csp_rule_follows_dearrow_thumbnails(self):
        ident = identity.cobalt_identity(machine="x86_64")
        [_, csp] = identity.dnr_rules(ident, identity.PageSettings())
        headers = {item["header"]: item["operation"] for item in csp["action"]["responseHeaders"]}
        self.assertEqual(headers, {"content-security-policy": "remove", "content-security-policy-report-only": "remove"})
        pattern = re.compile(csp["condition"]["regexFilter"])
        self.assertTrue(pattern.match("https://www.youtube.com/tv"))
        self.assertTrue(pattern.match("https://www.youtube.com/tv?env=1#/watch?v=x"))
        self.assertFalse(pattern.match("https://www.youtube.com/tv_static/app.js"))
        self.assertFalse(pattern.match("https://www.youtube.com/watch?v=x"))
        for settings in (identity.PageSettings(dearrow_thumbnails=False), identity.PageSettings(dearrow=False)):
            self.assertEqual([rule["id"] for rule in identity.dnr_rules(ident, settings)], [1])
        self.assertFalse(identity.page_config(None, identity.PageSettings(dearrow=False))["headerRules"])
        self.assertFalse(identity.page_config(None, identity.PageSettings(dearrow=False))["deArrowThumbnails"])

    def test_resolution_and_codec_normalisation(self):
        self.assertEqual(identity.normalise_resolution("1080P"), "1920x1080")
        self.assertEqual(identity.normalise_resolution(" screen "), "screen")
        self.assertEqual(identity.normalise_resolution("2560x1080"), "2560x1080")
        self.assertEqual(identity.normalise_resolution(""), "auto")
        for bad in ("huge", "0x0", "12x12"):
            with self.assertRaises(ValueError):
                identity.normalise_resolution(bad)
        self.assertEqual(identity.normalise_codecs(["VP9", " av1", "av1"]), ["av1", "vp9"])
        with self.assertRaises(ValueError):
            identity.normalise_codecs(["hevc"])

    def test_sponsorblock_categories(self):
        self.assertEqual(
            identity.normalise_sponsorblock_categories(["Sponsor", " intro", "sponsor", ""]),
            ["sponsor", "intro"],
        )
        with self.assertRaises(ValueError):
            identity.normalise_sponsorblock_categories(["sponsor", "ads"])

    def test_page_config_enables_community_services_by_default(self):
        config = identity.page_config(None, identity.PageSettings())
        self.assertTrue(config["sponsorBlock"])
        self.assertEqual(config["sponsorBlockCategories"], ["sponsor", "selfpromo", "interaction"])
        self.assertTrue(config["deArrow"])
        self.assertTrue(config["returnDislikes"])

    def test_write_extension_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            settings = identity.PageSettings(controller=False, cursor_hide_seconds=1.5, max_resolution="2160p")
            identity.write_extension_config(directory, identity.cobalt_identity(machine="x86_64"), settings)
            script = (directory / "config.js").read_text()
            match = re.fullmatch(r"globalThis\.__STEAMOS_YT_CONFIG__ = Object\.freeze\((.*)\);\n", script, re.S)
            self.assertIsNotNone(match)
            config = json.loads(match.group(1))
            self.assertFalse(config["controller"])
            self.assertEqual(config["cursorHideMs"], 1500)
            self.assertEqual(config["maxResolution"], "3840x2160")
            self.assertEqual(config["identity"]["platform"], "Starboard")
            rules = json.loads((directory / "rules.json").read_text())
            self.assertEqual([rule["id"] for rule in rules], [1, 2])
            self.assertTrue(config["headerRules"])


class LaunchPrepareTests(unittest.TestCase):
    def run_cli(self, *args):
        from contextlib import redirect_stderr, redirect_stdout
        from io import StringIO

        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            status = cli.main(list(args))
        return status, out.getvalue(), err.getvalue()

    def test_prints_cobalt_user_agent_and_writes_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            status, out, err = self.run_cli("launch-prepare", "--extension", tmp, "--url", "https://www.youtube.com/tv")
            self.assertEqual(status, 0)
            user_agent, open_url = out.splitlines()
            self.assertIn("Cobalt/", user_agent)
            self.assertTrue(open_url.startswith("data:text/html"))
            self.assertEqual(err, "")
            self.assertTrue((Path(tmp) / "config.js").exists())

    def test_opens_splash_page_that_forwards_to_target(self):
        from urllib.parse import unquote

        with tempfile.TemporaryDirectory() as tmp:
            target = "https://www.youtube.com/tv?a=1&b=</script>"
            _, out, _ = self.run_cli("launch-prepare", "--extension", tmp, "--url", target)
            open_url = out.splitlines()[1]
            self.assertTrue(open_url.startswith("data:text/html;charset=utf-8,"))
            page = unquote(open_url.split(",", 1)[1])
            self.assertIn(identity.SPLASH_MARKER, page)
            self.assertIn('location.replace("https://www.youtube.com/tv?a=1&b=\\u003c/script>")', page)
            self.assertEqual(page.count("</script>"), 1)
            self.assertNotIn("#", open_url)
            config = json.loads(re.search(r"Object\.freeze\((.*)\);", (Path(tmp) / "config.js").read_text(), re.S).group(1))
            self.assertEqual(config["targetUrl"], target)

    def test_splash_only_when_header_rules_exist(self):
        url = "https://www.youtube.com/tv"
        with tempfile.TemporaryDirectory() as tmp:
            _, out, _ = self.run_cli("launch-prepare", "--extension", tmp, "--url", url, "--user-agent", "X/1", "--dearrow", "0")
            self.assertEqual(out.splitlines(), ["X/1", url])
            _, out, _ = self.run_cli("launch-prepare", "--extension", tmp, "--url", url, "--user-agent", "X/1")
            self.assertTrue(out.splitlines()[1].startswith("data:text/html"))

    def test_custom_user_agent_disables_client_hints(self):
        with tempfile.TemporaryDirectory() as tmp:
            status, out, _ = self.run_cli("launch-prepare", "--extension", tmp, "--user-agent", "Custom/1.0")
            self.assertEqual((status, out.splitlines()), (0, ["Custom/1.0", ""]))
            rules = json.loads((Path(tmp) / "rules.json").read_text())
            self.assertEqual([rule["id"] for rule in rules], [2])

    def test_browser_identity_prints_nothing(self):
        status, out, _ = self.run_cli("launch-prepare", "--identity", "browser")
        self.assertEqual((status, out.splitlines()), (0, ["", ""]))

    def test_community_service_switches(self):
        with tempfile.TemporaryDirectory() as tmp:
            status, _, err = self.run_cli(
                "launch-prepare", "--extension", tmp, "--sponsorblock", "0", "--dearrow", "no",
                "--return-dislikes", "off", "--sponsorblock-categories", "Sponsor, intro bogus",
            )
            self.assertEqual(status, 0)
            self.assertIn("unknown SponsorBlock category bogus", err)
            match = re.search(r"Object\.freeze\((.*)\);", (Path(tmp) / "config.js").read_text(), re.S)
            config = json.loads(match.group(1))
            self.assertEqual(
                (config["sponsorBlock"], config["deArrow"], config["returnDislikes"], config["sponsorBlockCategories"]),
                (False, False, False, ["sponsor", "intro"]),
            )

    def test_invalid_settings_fall_back_with_warnings(self):
        with tempfile.TemporaryDirectory() as tmp:
            status, _, err = self.run_cli(
                "launch-prepare", "--extension", tmp, "--max-resolution", "huge",
                "--block-codecs", "hevc", "--cursor-hide", "soon",
            )
            self.assertEqual(status, 0)
            self.assertIn("unsupported resolution", err)
            self.assertIn("unknown codec", err)
            self.assertIn("cursor hide delay", err)
            match = re.search(r"Object\.freeze\((.*)\);", (Path(tmp) / "config.js").read_text(), re.S)
            config = json.loads(match.group(1))
            self.assertEqual((config["maxResolution"], config["blockCodecs"], config["cursorHideMs"]), ("auto", [], 3000))


if __name__ == "__main__":
    unittest.main()
