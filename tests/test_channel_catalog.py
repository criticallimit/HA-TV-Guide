"""Offline tests for XMLTV channel metadata (no Home Assistant dependency)."""

import importlib.util
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "tv_guide"
PACKAGE = "_tvguide_catalog_tests"
module = types.ModuleType(PACKAGE)
module.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = module

def _load(name):
    spec = importlib.util.spec_from_file_location(f"{PACKAGE}.{name}", ROOT / f"{name}.py")
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = loaded
    spec.loader.exec_module(loaded)
    return loaded

_load("xmltv")
parse_channel_catalog = _load("channel_catalog").parse_channel_catalog


class ChannelCatalogTests(unittest.TestCase):
    def test_names_and_order(self):
        xml = b'<tv><channel id="ard"><display-name lang="de">Das Erste</display-name></channel><channel id="zdf"><display-name>ZDF</display-name></channel><channel id="ard"><display-name>Duplicate</display-name></channel></tv>'
        self.assertEqual(parse_channel_catalog(xml), [
            {"id": "ard", "name": "Das Erste"},
            {"id": "zdf", "name": "ZDF"},
        ])

    def test_missing_display_name(self):
        self.assertEqual(parse_channel_catalog(b'<tv><channel id="a" /></tv>'), [{"id": "a", "name": "a"}])

    def test_overlong_station_ids_are_not_merged_by_truncation(self):
        prefix='x'*160
        xml=('<tv>'+''.join(f'<channel id="{station}"><display-name>Station {i}</display-name></channel>' for i,station in enumerate([prefix,prefix+'a',prefix+'b']))+'</tv>').encode()
        self.assertEqual(parse_channel_catalog(xml),[{'id':prefix,'name':'Station 0'}])

    def test_utf16_cannot_bypass_dtd_rejection(self):
        with self.assertRaises(ValueError):
            parse_channel_catalog('<!DOCTYPE tv [<!ENTITY x "expanded">]><tv><channel id="a"><display-name>&x;</display-name></channel></tv>'.encode('utf-16'))

    def test_reject_external_entities(self):
        with self.assertRaises(ValueError):
            parse_channel_catalog(b'<!DOCTYPE tv [<!ENTITY x "bad">]><tv/>')


if __name__ == "__main__":
    unittest.main()
