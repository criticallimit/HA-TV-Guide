"""Offline tests of the URL policy, without Home Assistant imports."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "tv_guide"))
from feed_url import validate_feed_url  # noqa: E402


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
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_feed_url(value)


if __name__ == "__main__":
    unittest.main()
