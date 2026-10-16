"""Country baseline selection tests without Home Assistant."""
import importlib.util
import unittest
import json
import sys
import types
from pathlib import Path


def load_module(name):
    """Load pure helpers without shadowing standard-library modules."""
    path = Path(__file__).resolve().parents[1] / "custom_components" / "tv_guide" / f"{name}.py"
    package = types.ModuleType("_tvguide_country_tests"); package.__path__ = [str(path.parent)]
    sys.modules[package.__name__] = package
    spec = importlib.util.spec_from_file_location(package.__name__ + "." + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

_module = load_module("country_sources")
COUNTRY_FEEDS = _module.COUNTRY_FEEDS
effective_feed = _module.effective_feed
_module = load_module("feed_url")
validate_feed_url = _module.validate_feed_url


class CountrySourceTests(unittest.TestCase):
    def test_country_fallbacks_and_explicit_override(self):
        sources = load_module("country_sources")
        countries = json.loads((Path(__file__).resolve().parents[1] / "custom_components/tv_guide/countries.json").read_text())
        for country, config in countries.items():
            candidates = sources.feed_candidates({"country": country})
            self.assertEqual(candidates, tuple(config['sources']))
            self.assertEqual(candidates[0], COUNTRY_FEEDS[country])
            for url in candidates:
                self.assertEqual(validate_feed_url(url), url)
            # Even a manual URL identical to the baseline must stay authoritative.
            self.assertEqual(sources.feed_candidates({"country": country, "feed_url": candidates[0]}), (candidates[0],))
        self.assertEqual(sources.feed_candidates({"country": "at"}), (COUNTRY_FEEDS["at"],))
        self.assertEqual(sources.feed_candidates({}), ())

    def test_all_registered_sources_have_safe_syntax(self):
        countries = json.loads((Path(__file__).resolve().parents[1] / "custom_components/tv_guide/countries.json").read_text())
        self.assertEqual(set(COUNTRY_FEEDS), set(countries))
        for source in COUNTRY_FEEDS.values():
            self.assertEqual(validate_feed_url(source), source)

    def test_selection_and_overrides(self):
        self.assertEqual(effective_feed({"country": "dk"}), COUNTRY_FEEDS["dk"])
        self.assertEqual(effective_feed({"country": "dk", "feed_url": "https://example.org/test.xml"}), "https://example.org/test.xml")
        self.assertIsNone(effective_feed({}))
        self.assertIsNone(effective_feed({"country": "none"}))


if __name__ == "__main__":
    unittest.main()
