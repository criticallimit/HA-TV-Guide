"""UTC/DST safe reminder scheduling tests; no Home Assistant imports."""

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "tv_guide"))
from reminder_times import next_reminder_time, retry_time


class ReminderTimeTests(unittest.TestCase):
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
