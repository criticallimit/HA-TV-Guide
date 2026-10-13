"""Tests for translating stable main-channel IDs to feed IDs."""

import importlib.util
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "tv_guide"
PACKAGE = "_tvguide_mapping_tests"
pkg = types.ModuleType(PACKAGE)
pkg.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = pkg
spec = importlib.util.spec_from_file_location(f"{PACKAGE}.channel_mapping", ROOT / "channel_mapping.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class ChannelMappingTests(unittest.TestCase):
    def test_canonical_ids_translate_to_feed(self):
        catalogue = [
            {"id": "ard", "name": "Das Erste", "xmltv_id": "DasErste.de"},
            {"id": "zdf", "name": "ZDF", "xmltv_id": "ZDF.de"},
        ]
        self.assertEqual(module.resolved_selection(["zdf", "ard"], catalogue), ["ZDF.de", "DasErste.de"])
        self.assertEqual(module.channel_labels(catalogue, [{"id": "DasErste.de", "name": "ARD"}])["DasErste.de"], "Das Erste")

    def test_unavailable_canonical_channel_is_not_reinterpreted(self):
        catalogue = [{"id": "ard", "name": "Das Erste", "xmltv_id": None}]
        self.assertEqual(module.resolved_selection(["ard"], catalogue), [])

    def test_empty_selection(self):
        self.assertEqual(module.resolved_selection([], []), [])


if __name__ == "__main__":
    unittest.main()
