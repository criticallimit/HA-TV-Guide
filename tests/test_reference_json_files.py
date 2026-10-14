"""User JSON files recover safely without losing an existing file on failed writes."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reference_support import app
import sys
json_files = sys.modules[app.__package__ + ".json_files"]
read_json_file, write_json_file = json_files.read_json_file, json_files.write_json_file


class JsonFileTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "saved.json"

    def test_missing_invalid_and_wrong_root_use_defaults(self):
        self.assertEqual(read_json_file(self.path, {}), {})
        for raw in ['broken', 'null', '[]', '42', '"text"']:
            with self.subTest(raw=raw):
                self.path.write_text(raw, encoding="utf-8")
                self.assertEqual(read_json_file(self.path, {}), {})
        self.path.write_bytes(b'\xff')
        self.assertEqual(read_json_file(self.path, []), [])

    def test_unicode_round_trip_for_settings_and_lists(self):
        for value in [{"country": "no", "title": "Blå"}, [{"title": "Grüße"}]]:
            write_json_file(self.path, value)
            self.assertEqual(read_json_file(self.path, type(value)()), value)
            self.assertFalse(self.path.with_suffix(".tmp").exists())

    def test_failed_serialization_keeps_previous_file(self):
        write_json_file(self.path, {"country": "be"})
        with self.assertRaises(TypeError):
            write_json_file(self.path, {"invalid": object()})
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), {"country": "be"})

    def test_failed_replacement_keeps_previous_file(self):
        write_json_file(self.path, {"country": "be"})
        with patch.object(json_files.os, "replace", side_effect=OSError("unavailable")):
            with self.assertRaises(OSError):
                write_json_file(self.path, {"country": "no"})
        self.assertEqual(read_json_file(self.path, {}), {"country": "be"})
        write_json_file(self.path, {"country": "nl"})
        self.assertEqual(read_json_file(self.path, {}), {"country": "nl"})

    def test_wrong_root_cannot_break_settings_or_country_preferences(self):
        with patch.multiple(app, OPTIONS_FILE=self.path, CHANNEL_PREFS_FILE=self.path):
            for value in [None, [], 42, "old"]:
                with self.subTest(value=value):
                    self.path.write_text(json.dumps(value), encoding="utf-8")
                    self.assertEqual(app.load_options()["country"], "de")
                    self.assertEqual(app.load_options_ui()["default_view"], "now")
                    self.assertEqual(app.load_channel_preferences(app.EPGStore("de"))["hidden"], [])


if __name__ == "__main__":
    unittest.main()
