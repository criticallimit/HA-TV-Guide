"""Country baseline selection tests without Home Assistant."""
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

_module = load_module("country_sources")
COUNTRY_FEEDS = _module.COUNTRY_FEEDS
effective_feed = _module.effective_feed
_module = load_module("feed_url")
validate_feed_url = _module.validate_feed_url


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
