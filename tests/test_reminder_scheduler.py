"""Offline regression tests for reminder lifecycle and delivery."""

import asyncio
import importlib.util
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "tv_guide"
PKG = "_tvguide_scheduler_tests"
package = types.ModuleType(PKG)
package.__path__ = [str(ROOT)]
sys.modules[PKG] = package

homeassistant = types.ModuleType("homeassistant")
homeassistant.__path__ = []
helpers = types.ModuleType("homeassistant.helpers")
helpers.__path__ = []
event = types.ModuleType("homeassistant.helpers.event")
timers = []

def schedule(hass, callback, when):
    entry = {"callback": callback, "when": when, "cancelled": False}
    timers.append(entry)
    def cancel():
        entry["cancelled"] = True
    return cancel

event.async_track_point_in_utc_time = schedule
sys.modules.setdefault("homeassistant", homeassistant)
sys.modules.setdefault("homeassistant.helpers", helpers)
sys.modules.setdefault("homeassistant.helpers.event", event)

for name in ("reminder_times", "reminder_scheduler"):
    spec = importlib.util.spec_from_file_location(f"{PKG}.{name}", ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

Scheduler = sys.modules[f"{PKG}.reminder_scheduler"].TVGuideReminderScheduler

class Services:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail
    async def async_call(self, domain, service, payload, blocking=False):
        self.calls.append((domain, service, payload, blocking))
        if self.fail:
            raise RuntimeError("temporary failure")

class Saved:
    def __init__(self, record):
        self.reminders = [record]
        self.saves = 0
    async def async_save(self):
        self.saves += 1

class SchedulerTests(unittest.TestCase):
    def setUp(self):
        timers.clear()

    def _make(self, fail=False):
        start = datetime.now(timezone.utc) + timedelta(minutes=9)
        record = {"id": "test", "start": start.isoformat(), "minutes": 10, "channel": "ARD", "title": "Nachrichten"}
        saved = Saved(record)
        hass = types.SimpleNamespace(
            config=types.SimpleNamespace(time_zone="Europe/Berlin"),
            services=Services(fail),
            async_create_task=asyncio.create_task,
        )
        return Scheduler(hass, saved, asyncio.Lock()), saved, hass

    def test_stop_cancels_timers_and_cannot_be_rearmed(self):
        scheduler, saved, hass = self._make()
        scheduler.reschedule()
        self.assertEqual(len(timers), 1)
        scheduler.stop()
        self.assertTrue(timers[0]["cancelled"])
        scheduler.reschedule()
        self.assertEqual(len(timers), 1)
        asyncio.run(scheduler._deliver("test"))
        self.assertEqual(hass.services.calls, [])

    def test_success_marks_sent_once(self):
        async def run():
            scheduler, saved, hass = self._make()
            await scheduler._deliver("test")
            await scheduler._deliver("test")
            self.assertEqual(len(hass.services.calls), 1)
            self.assertTrue(saved.reminders[0]["sent"])
            self.assertEqual(saved.saves, 1)
        asyncio.run(run())

    def test_failure_does_not_mark_sent(self):
        async def run():
            scheduler, saved, hass = self._make(fail=True)
            await scheduler._deliver("test")
            self.assertFalse(saved.reminders[0].get("sent", False))
            self.assertEqual(saved.saves, 0)
            self.assertTrue(timers)
        asyncio.run(run())

if __name__ == "__main__":
    unittest.main()
