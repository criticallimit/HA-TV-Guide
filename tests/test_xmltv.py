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

    def test_dates_outside_utc_range_are_skipped_without_losing_valid_programmes(self):
        self.assertIsNone(parse_xmltv_time('99991231233000 -0100'))
        self.assertIsNone(parse_xmltv_time('00010101000000 +0100'))
        data=b'<tv><programme channel="bad" start="99991231233000 -0100" stop="99991231234500 -0100"><title>Invalid</title></programme><programme channel="good" start="20300101120000 +0000" stop="20300101130000 +0000"><title>Valid</title></programme></tv>'
        self.assertEqual([row['title'] for row in parse_xmltv(data)],['Valid'])

    def test_programmes(self):
        xml = b'<tv><programme channel="channel.one" start="20261013201500 +0200" stop="20261013220000 +0200"><title lang="de">Film</title><desc>Beschreibung</desc></programme></tv>'
        result = parse_xmltv(xml)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["channel"], "channel.one")
        self.assertEqual(result[0]["title"], "Film")
        self.assertEqual(result[0]["description"], "Beschreibung")

    def test_overlong_station_ids_are_not_merged_by_truncation(self):
        prefix='x'*160
        xml=('<tv>'+''.join(f'<programme channel="{station}" start="20300101120000 +0000" stop="20300101130000 +0000"><title>Station {i}</title></programme>' for i,station in enumerate([prefix,prefix+'a',prefix+'b']))+'</tv>').encode()
        records=parse_xmltv(xml)
        self.assertEqual([(row['channel'],row['title']) for row in records],[(prefix,'Station 0')])

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
