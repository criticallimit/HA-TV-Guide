"""Offline XMLTV reader tests."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "tv_guide"))
from xmltv import parse_xmltv, parse_xmltv_time  # noqa: E402


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

    def test_invalid(self):
        self.assertEqual(parse_xmltv(b'<tv><programme channel="a"/></tv>'), [])
        with self.assertRaises(ValueError):
            parse_xmltv(b'<!DOCTYPE tv [<!ENTITY x "bad">]><tv/>')
        with self.assertRaises(ValueError):
            parse_xmltv(b"x" * (8 * 1024 * 1024 + 1))


if __name__ == "__main__":
    unittest.main()
