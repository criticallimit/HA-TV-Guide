"""UTC/DST safe reminder scheduling tests; no Home Assistant imports."""

import importlib.util
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


def load_module(name):
    """Load pure helpers without shadowing standard-library modules."""
    path = Path(__file__).resolve().parents[1] / "custom_components" / "tv_guide" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

_module = load_module("reminder_times")
next_reminder_time = _module.next_reminder_time
retry_time = _module.retry_time


class ReminderTimeTests(unittest.TestCase):
    def test_unrepresentable_dates_and_fractional_minutes_are_inert(self):
        now=datetime(2026,10,14,tzinfo=timezone.utc)
        for start in ('9999-12-31T23:59:59+00:00','9999-12-31T23:30:00-01:00','0001-01-01T00:00:00+01:00'):
            record={'start':start,'minutes':10}
            self.assertIsNone(next_reminder_time(record,now))
            self.assertIsNone(retry_time(record,now))
        self.assertIsNone(next_reminder_time({'start':'2026-10-14T00:10:00+00:00','minutes':10.5},now))

    def test_short_programme_end_bounds_delivery_and_retry(self):
        now=datetime(2026,10,14,18,0,tzinfo=timezone.utc)
        record={'start':now.isoformat(),'end':(now+timedelta(seconds=30)).isoformat(),'minutes':10}
        self.assertEqual(next_reminder_time(record,now),now)
        self.assertIsNone(retry_time(record,now))
        self.assertIsNone(next_reminder_time(record,now+timedelta(seconds=30)))

    def test_offset_and_utc(self):
        now = datetime(2026, 10, 13, 18, 0, tzinfo=timezone.utc)
        record = {"start": "2026-10-13T20:15:00+02:00", "minutes": 15, "sent": False}
        self.assertEqual(next_reminder_time(record, now), now)
        early = now - timedelta(hours=1)
        self.assertEqual(next_reminder_time(record, early), now)

    def test_sent_and_expired(self):
        now = datetime(2026, 10, 13, 18, 30, tzinfo=timezone.utc)
        record = {"start": "2026-10-13T20:15:00+02:00", "minutes": 5}
        self.assertIsNone(next_reminder_time(record, now))
        self.assertIsNone(next_reminder_time({**record, "sent": True}, now - timedelta(hours=1)))

    def test_retry_is_bounded(self):
        now = datetime(2026, 10, 13, 18, 0, tzinfo=timezone.utc)
        record = {"start": "2026-10-13T20:15:00+02:00"}
        self.assertEqual(retry_time(record, now), now + timedelta(seconds=60))
        self.assertIsNone(retry_time(record, now + timedelta(minutes=20)))


if __name__ == "__main__":
    unittest.main()
