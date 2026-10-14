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
pending_reminders = sys.modules[f"{PKG}.next_reminder"].pending_reminders


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

    def test_overdue_sensor_retains_original_due_time(self):
        now=datetime(2026,10,14,18,0,tzinfo=timezone.utc)
        record={'id':'due','start':(now+timedelta(minutes=2)).isoformat(),'minutes':10}
        when,item=next_pending_reminder([record],now)
        self.assertEqual(when,now-timedelta(minutes=8))
        self.assertIs(item,record)

    def test_pending_count_omits_sent_and_grace_expired_reminders(self):
        now=datetime(2026,10,14,18,0,tzinfo=timezone.utc)
        records=[{'id':str(i),'start':(now+timedelta(minutes=offset)).isoformat(),'minutes':10,'sent':sent}
                 for i,(offset,sent) in enumerate([(10,False),(20,True),(-6,False)])]
        self.assertEqual(len(pending_reminders(records,now)),1)


if __name__ == "__main__":
    unittest.main()
