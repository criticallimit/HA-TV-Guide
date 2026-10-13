"""Offline tests for original bundled sender lists and EPG ID matching."""

import importlib.util
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "tv_guide"
PACKAGE = "_tvguide_bundled_catalog_tests"
module = types.ModuleType(PACKAGE)
module.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = module
spec = importlib.util.spec_from_file_location(f"{PACKAGE}.catalogs", ROOT / "catalogs.py")
loaded = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = loaded
spec.loader.exec_module(loaded)


class OriginalCatalogueTests(unittest.TestCase):
    def test_all_ten_countries_have_ordered_main_channels(self):
        self.assertEqual(len(loaded.CATALOG_FILES), 10)
        for country in loaded.CATALOG_FILES:
            with self.subTest(country=country):
                channels = loaded.load_channel_catalog(country)
                self.assertTrue(channels)
                orders = [channel["order"] for channel in channels]
                self.assertEqual(orders, sorted(orders))
                self.assertEqual(len({channel["id"] for channel in channels}), len(channels))

    def test_known_german_xmltv_id(self):
        matched = loaded.resolve_catalogue_channels("de", [
            {"id": "DasErste.de", "name": "Das Erste HD"}
        ])
        self.assertEqual(matched[0]["id"], "ard")
        self.assertEqual(matched[0]["xmltv_id"], "DasErste.de")
        self.assertTrue(matched[0]["available"])
        self.assertEqual(matched[1]["id"], "zdf")
        self.assertFalse(matched[1]["available"])

    def test_unknown_country(self):
        self.assertEqual(loaded.resolve_catalogue_channels("invalid", []), [])


if __name__ == "__main__":
    unittest.main()
