"""Offline tests for saved channel selection."""

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

_module = load_module("channel_selection")
filter_programmes = _module.filter_programmes
parse_channel_selection = _module.parse_channel_selection


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
