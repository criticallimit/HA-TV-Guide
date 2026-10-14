"""Offline tests of the URL policy, without Home Assistant imports."""

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

_module = load_module("feed_url")
validate_feed_url = _module.validate_feed_url


class FeedURLTests(unittest.TestCase):
    def test_public_https_url(self):
        self.assertEqual(
            validate_feed_url("https://example.org/feed.xml.gz"),
            "https://example.org/feed.xml.gz",
        )

    def test_rejects_unsafe_urls(self):
        invalid = (
            "http://example.org/feed", "file:///etc/passwd", "https://localhost/feed",
            "https://host.local/feed", "https://host.internal/feed",
            "https://127.0.0.1/feed", "https://192.168.1.1/feed",
            "https://169.254.169.254/latest/meta-data", "https://[::1]/feed",
            "https://user:pass@example.org/feed", "https://example.org:8443/feed",
            "https://example.org/feed#fragment", "https://example.org/feed\n",
            "https://singlelabel/feed", "https://example.org:bad/feed",
            "https://8.8.8.8/feed", "https://[2606:4700:4700::1111]/feed",
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_feed_url(value)


if __name__ == "__main__":
    unittest.main()
