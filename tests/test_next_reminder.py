"""Offline tests for selecting the earliest native reminder."""

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "tv_guide"
PKG = "_tvguide_next_reminder_tests"
package = types.ModuleType(PKG)
package.__path__ = [str(ROOT)]
sys.modules[PKG] = package
for name in ("reminder_times", "next_reminder"):
    spec = importlib.util.spec_from_file_location(f"{PKG}.{name}", ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

next_pending_reminder = sys.modules[f"{PKG}.next_reminder"].next_pending_reminder


class NextReminderTests(unittest.TestCase):
    def test_earliest_unsent_and_metadata(self):
        now = datetime(2026, 10, 13, 16, 0, tzinfo=timezone.utc)
        later = {"id": "later", "start": "2026-10-13T19:30:00+02:00", "minutes": 10}
        first = {"id": "first", "start": "2026-10-13T19:00:00+02:00", "minutes": 15}
        when, item = next_pending_reminder([later, first], now)
        self.assertEqual(when, datetime(2026, 10, 13, 16, 45, tzinfo=timezone.utc))
        self.assertIs(item, first)

    def test_sent_and_expired(self):
        now = datetime(2026, 10, 13, 18, 0, tzinfo=timezone.utc)
        data = [
            {"id": "sent", "start": "2026-10-13T20:30:00+02:00", "minutes": 10, "sent": True},
            {"id": "expired", "start": "2026-10-13T19:00:00+02:00", "minutes": 10},
        ]
        self.assertEqual(next_pending_reminder(data, now), (None, None))


if __name__ == "__main__":
    unittest.main()
