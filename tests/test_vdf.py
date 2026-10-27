import struct
import unittest

import _paths  # noqa: F401
from steamos_yt import vdf


def cstr(text: str) -> bytes:
    return text.encode("utf-8") + b"\x00"


def int32(key: str, value: int) -> bytes:
    return bytes([vdf.INT32]) + cstr(key) + struct.pack("<i", value)


def string(key: str, value: str) -> bytes:
    return bytes([vdf.STRING]) + cstr(key) + cstr(value)


def mapping(key: str, body: bytes) -> bytes:
    return bytes([vdf.MAP]) + cstr(key) + body + bytes([vdf.END])


STEAM_WRITTEN = mapping(
    "shortcuts",
    mapping(
        "0",
        int32("appid", -1234567890)
        + string("AppName", "Some Game")
        + string("Exe", '"/opt/game/run.sh"')
        + string("StartDir", '"/opt/game/"')
        + string("icon", "")
        + string("ShortcutPath", "")
        + string("LaunchOptions", "--fullscreen")
        + int32("IsHidden", 0)
        + int32("AllowDesktopConfig", 1)
        + int32("AllowOverlay", 1)
        + int32("OpenVR", 0)
        + int32("Devkit", 0)
        + string("DevkitGameID", "")
        + int32("DevkitOverrideAppID", 0)
        + int32("LastPlayTime", 1700000000)
        + string("FlatpakAppID", "")
        + mapping("tags", string("0", "Favorite")),
    ),
) + bytes([vdf.END])


class BinaryVdfTests(unittest.TestCase):
    def test_round_trip_is_byte_identical(self):
        root = vdf.loads_binary(STEAM_WRITTEN)
        self.assertEqual(vdf.dumps_binary(root), STEAM_WRITTEN)

    def test_decodes_nested_values(self):
        root = vdf.loads_binary(STEAM_WRITTEN)
        entry = root.get("shortcuts").get("0")
        self.assertEqual(entry.get("appid"), -1234567890)
        self.assertEqual(entry.get("LaunchOptions"), "--fullscreen")
        self.assertEqual(entry.get("tags").get("0"), "Favorite")

    def test_every_value_type_round_trips(self):
        body = (
            int32("int", -5)
            + bytes([vdf.FLOAT32]) + cstr("float") + struct.pack("<f", 1.5)
            + bytes([vdf.POINTER]) + cstr("pointer") + struct.pack("<I", 7)
            + bytes([vdf.WSTRING]) + cstr("wide") + "wïde".encode("utf-16-le") + b"\x00\x00"
            + bytes([vdf.COLOR]) + cstr("color") + struct.pack("<I", 0xFF00FF00)
            + bytes([vdf.UINT64]) + cstr("uint64") + struct.pack("<Q", 2 ** 63 + 5)
            + bytes([vdf.INT64]) + cstr("int64") + struct.pack("<q", -(2 ** 40))
            + string("text", "naïve ✓")
        )
        data = mapping("root", body) + bytes([vdf.END])
        root = vdf.loads_binary(data)
        values = root.get("root").to_dict()
        self.assertEqual(values["float"], 1.5)
        self.assertEqual(values["wide"], "wïde")
        self.assertEqual(values["uint64"], 2 ** 63 + 5)
        self.assertEqual(values["text"], "naïve ✓")
        self.assertEqual(vdf.dumps_binary(root), data)

    def test_invalid_utf8_is_preserved(self):
        data = mapping("shortcuts", bytes([vdf.STRING]) + cstr("name") + b"caf\xe9\x00") + bytes([vdf.END])
        self.assertEqual(vdf.dumps_binary(vdf.loads_binary(data)), data)

    def test_missing_final_terminator_is_tolerated(self):
        root = vdf.loads_binary(STEAM_WRITTEN[:-1])
        self.assertIn("shortcuts", root)

    def test_truncated_data_raises(self):
        with self.assertRaises(vdf.VdfError):
            vdf.loads_binary(STEAM_WRITTEN[:40])

    def test_unknown_type_raises(self):
        with self.assertRaises(vdf.VdfError):
            vdf.loads_binary(b"\x09bad\x00\x08")

    def test_keys_are_case_insensitive_and_keep_spelling(self):
        node = vdf.KeyValues()
        node.set("AppName", "One")
        node.set("appname", "Two")
        self.assertEqual(list(node), ["AppName"])
        self.assertEqual(node.get("APPNAME"), "Two")
        self.assertTrue(node.remove("appNAME"))
        self.assertNotIn("AppName", node)

    def test_set_keeps_existing_numeric_type(self):
        node = vdf.KeyValues()
        node.set("big", 1, vdf.UINT64)
        node.set("big", 2)
        self.assertEqual(node.type_of("big"), vdf.UINT64)
        node.set("big", "text")
        self.assertEqual(node.type_of("big"), vdf.STRING)

    def test_out_of_range_value_is_rejected_on_encode(self):
        node = vdf.KeyValues()
        node.set("n", 2 ** 40, vdf.INT32)
        with self.assertRaises(vdf.VdfError):
            vdf.dumps_binary(node)


LOGINUSERS = r'''
"users"
{
	// the most recent account wins
	"76561197960287930"
	{
		"AccountName"		"deck_user"
		"PersonaName"		"Deck \"User\""
		"MostRecent"		"1"
		"Timestamp"		"1761500000"
	}
	"76561198000000000"
	{
		"AccountName"		"other"
		"MostRecent"		"0"
		"Timestamp"		"1761000000" [$LINUX]
	}
}
'''


class TextVdfTests(unittest.TestCase):
    def test_parses_loginusers(self):
        root = vdf.loads_text(LOGINUSERS)
        users = root.get("users")
        first = users.get("76561197960287930")
        self.assertEqual(first.get("PersonaName"), 'Deck "User"')
        self.assertEqual(first.get("mostrecent"), "1")
        self.assertEqual(users.get("76561198000000000").get("Timestamp"), "1761000000")

    def test_unbalanced_braces_raise(self):
        with self.assertRaises(vdf.VdfError):
            vdf.loads_text('"a" { "b" "c"')
        with self.assertRaises(vdf.VdfError):
            vdf.loads_text('"a" "b" }')


if __name__ == "__main__":
    unittest.main()
