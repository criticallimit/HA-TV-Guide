"""Offline XMLTV reader tests."""
import importlib.util
import unittest
from pathlib import Path


def load_module(name):
    """Load pure helpers without shadowing standard-library modules."""
    path = Path(__file__).resolve().parents[1] / "custom_components" / "tv_guide" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

_module = load_module("xmltv")
parse_xmltv = _module.parse_xmltv
parse_xmltv_time = _module.parse_xmltv_time


class XMLTVTests(unittest.TestCase):
    def test_time(self):
        parsed = parse_xmltv_time("20261013201500 +0200")
        self.assertEqual(parsed.isoformat(), "2026-10-13T18:15:00+00:00")
        self.assertIsNone(parse_xmltv_time("20261013201500"))
        self.assertIsNone(parse_xmltv_time("wrong"))

    def test_programmes(self):
        xml = b'<tv><programme channel="channel.one" start="20261013201500 +0200" stop="20261013220000 +0200"><title lang="de">Film</title><desc>Beschreibung</desc></programme></tv>'
        result = parse_xmltv(xml)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["channel"], "channel.one")
        self.assertEqual(result[0]["title"], "Film")
        self.assertEqual(result[0]["description"], "Beschreibung")

    def test_utf16_cannot_bypass_dtd_rejection(self):
        xml = '<!DOCTYPE tv [<!ENTITY x "expanded">]><tv><programme channel="a" start="20261014190000 +0000" stop="20261014200000 +0000"><title>&x;</title></programme></tv>'
        with self.assertRaises(ValueError):
            parse_xmltv(xml.encode('utf-16'))

    def test_invalid(self):
        self.assertEqual(parse_xmltv(b'<tv><programme channel="a"/></tv>'), [])
        with self.assertRaises(ValueError):
            parse_xmltv(b'<!DOCTYPE tv [<!ENTITY x "bad">]><tv/>')
        with self.assertRaises(ValueError):
            parse_xmltv(b"x" * (8 * 1024 * 1024 + 1))


if __name__ == "__main__":
    unittest.main()
