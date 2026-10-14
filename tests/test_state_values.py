"""Offline unit tests for safe native value conversion."""

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

_module = load_module("state_values")
owned_state = _module.owned_state
parse_count = _module.parse_count
parse_timestamp = _module.parse_timestamp


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
