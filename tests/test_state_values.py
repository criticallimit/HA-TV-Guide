"""Offline unit tests for safe native value conversion."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "tv_guide"))
from state_values import owned_state, parse_count, parse_timestamp  # noqa: E402


class StateValueTests(unittest.TestCase):
    def test_count(self):
        self.assertEqual(parse_count("0"), 0)
        self.assertEqual(parse_count("12"), 12)
        for invalid in ("unknown", "unavailable", "-1", "1.5", "", None, "²"):
            self.assertIsNone(parse_count(invalid))

    def test_timestamp(self):
        self.assertEqual(
            parse_timestamp("2026-10-13T19:00:00+02:00").utcoffset().total_seconds(),
            7200,
        )
        self.assertIsNotNone(parse_timestamp("2026-10-13T17:00:00Z"))
        for invalid in ("unknown", "", None, "2026-10-13T19:00:00"):
            self.assertIsNone(parse_timestamp(invalid))

    def test_source_marker(self):
        self.assertTrue(owned_state({"tv_guide_source": "criticallimit/TV-Guide"}, "criticallimit/TV-Guide"))
        self.assertFalse(owned_state({}, "criticallimit/TV-Guide"))
        self.assertFalse(owned_state(None, "criticallimit/TV-Guide"))


if __name__ == "__main__":
    unittest.main()
