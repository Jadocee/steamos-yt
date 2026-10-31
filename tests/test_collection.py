import json
import tempfile
import unittest
from pathlib import Path

import _fakes
from nonsteamapps import collection

ACCOUNT = 111


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path = _fakes.make_cloud_storage(self.root, ACCOUNT)

    def tearDown(self):
        self.tmp.cleanup()

    def entries(self):
        return {key: value for key, value in json.loads(self.path.read_text())}

    def test_steams_current_namespace_is_used_once_it_exists(self):
        self.assertEqual(collection.storage_file(self.root, ACCOUNT), self.path)
        other = _fakes.make_cloud_storage(self.root, ACCOUNT, namespace=3)
        self.assertEqual(collection.storage_file(self.root, ACCOUNT), other)
        self.assertIsNone(collection.storage_file(self.root, 222))

    def test_apps_go_in_and_out_without_touching_other_collections(self):
        self.assertTrue(collection.update(self.path, "NonSteamApps", add=[3000000001, 3000000002]))
        self.assertFalse(collection.update(self.path, "NonSteamApps", add=[3000000002]))
        entry = self.entries()[collection.KEY]
        self.assertEqual(json.loads(entry["value"]), {"id": "nonsteamapps", "name": "NonSteamApps", "added": [3000000001, 3000000002], "removed": []})
        self.assertEqual((entry["conflictResolutionMethod"], entry["strMethodId"]), ("custom", "union-collections"))
        self.assertEqual(entry["version"], str(entry["timestamp"]))
        self.assertTrue(collection.update(self.path, "Living room", remove=[3000000001]))
        self.assertEqual(json.loads(self.entries()[collection.KEY]["value"])["removed"], [3000000001])
        self.assertEqual(json.loads(self.entries()[collection.KEY]["value"])["name"], "Living room")
        self.assertEqual(collection.members(self.path), [3000000002])
        for key, original in _fakes.USER_COLLECTIONS:
            self.assertEqual(self.entries()[key], original)

    def test_an_empty_collection_is_deleted_and_can_come_back(self):
        collection.update(self.path, "NonSteamApps", add=[3000000001])
        self.assertTrue(collection.update(self.path, "NonSteamApps", remove=[3000000001]))
        self.assertTrue(self.entries()[collection.KEY]["is_deleted"])
        self.assertEqual(collection.members(self.path), [])
        self.assertFalse(collection.delete(self.path))
        collection.update(self.path, "NonSteamApps", add=[3000000001])
        self.assertNotIn("is_deleted", self.entries()[collection.KEY])
        self.assertTrue(collection.delete(self.path))
        self.assertTrue(self.entries()[collection.KEY]["is_deleted"])

    def test_an_unreadable_file_is_left_alone(self):
        self.path.write_text("{broken")
        self.assertFalse(collection.update(self.path, "NonSteamApps", add=[3000000001]))
        self.assertEqual(self.path.read_text(), "{broken")


if __name__ == "__main__":
    unittest.main()
