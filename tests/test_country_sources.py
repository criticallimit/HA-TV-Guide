"""Country baseline selection tests without Home Assistant."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "tv_guide"))
from country_sources import COUNTRY_FEEDS, effective_feed
from feed_url import validate_feed_url


class CountrySourceTests(unittest.TestCase):
    def test_ten_sources_have_safe_syntax(self):
        self.assertEqual(len(COUNTRY_FEEDS), 10)
        for source in COUNTRY_FEEDS.values():
            self.assertEqual(validate_feed_url(source), source)

    def test_selection_and_overrides(self):
        self.assertEqual(effective_feed({"country": "dk"}), COUNTRY_FEEDS["dk"])
        self.assertEqual(effective_feed({"country": "dk", "feed_url": "https://example.org/test.xml"}), "https://example.org/test.xml")
        self.assertIsNone(effective_feed({}))
        self.assertIsNone(effective_feed({"country": "none"}))


if __name__ == "__main__":
    unittest.main()
