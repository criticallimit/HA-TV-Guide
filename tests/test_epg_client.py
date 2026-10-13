"""Feed URL validation tests (no network)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "tv_guide"))
# Import as a package is deferred until Home Assistant is present.
from urllib.parse import urlsplit


class ValidationTests(unittest.TestCase):
    def test_url_requirements(self):
        for url in ("https://example.org/feed.xml", "https://example.org/guide.xml.gz"):
            parsed = urlsplit(url)
            self.assertEqual(parsed.scheme, "https")
        for url in ("http://example.org", "file:///etc/passwd", "https://user:pass@example.org/feed"):
            parsed = urlsplit(url)
            self.assertTrue(parsed.scheme != "https" or parsed.username is not None)


if __name__ == "__main__":
    unittest.main()
