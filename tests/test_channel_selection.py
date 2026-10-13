"""Offline tests for saved channel selection."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "tv_guide"))
from channel_selection import filter_programmes, parse_channel_selection  # noqa: E402


class ChannelSelectionTests(unittest.TestCase):
    def test_persist_order_and_deduplicate(self):
        self.assertEqual(parse_channel_selection("zdf, ard\nzdf, arte"), ["zdf", "ard", "arte"])

    def test_no_selection_means_all(self):
        records = [{"channel": "ard"}, {"channel": "zdf"}, {"channel": "arte"}]
        self.assertEqual(filter_programmes(records, []), records)
        self.assertEqual(filter_programmes(records, ["zdf", "ard"]), records[:2])

    def test_invalid_selection(self):
        for value in ("x" * 161, "a\x00b", ",".join(str(i) for i in range(201))):
            with self.subTest(value=value[:20]), self.assertRaises(ValueError):
                parse_channel_selection(value)


if __name__ == "__main__":
    unittest.main()
