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

core = sys.modules.setdefault("homeassistant.core", types.ModuleType("homeassistant.core"))
def mark_callback(func):
    func._hass_callback = True
    return func
core.callback = mark_callback

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
        async def executor(fn,*args):return fn(*args)
        hass = types.SimpleNamespace(
            config=types.SimpleNamespace(time_zone="Europe/Berlin"),
            services=Services(fail),
            async_create_task=asyncio.create_task,
            async_add_executor_job=executor,
        )
        return Scheduler(hass, saved, asyncio.Lock()), saved, hass

    def test_timer_is_ha_callback_and_stale_generation_is_ignored(self):
        scheduler, saved, hass = self._make()
        scheduler.reschedule()
        old = timers[0]["callback"]
        self.assertTrue(getattr(old, "_hass_callback", False))
        scheduler.reschedule()
        queued = []
        hass.async_create_task = lambda coro: queued.append(coro)
        old(datetime.now(timezone.utc))
        self.assertEqual(queued, [])

    def test_future_reminder_cannot_be_delivered_by_old_callback(self):
        async def run():
            scheduler, saved, hass = self._make()
            saved.reminders[0]["start"] = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
            await scheduler._deliver("test")
            self.assertEqual(hass.services.calls, [])
        asyncio.run(run())

    def test_storage_retry_never_resends_successful_notification(self):
        async def run():
            scheduler, saved, hass = self._make()
            original = saved.async_save
            async def fail():
                raise OSError("storage failure")
            saved.async_save = fail
            await scheduler._deliver("test")
            self.assertTrue(saved.reminders[0]["sent"])
            self.assertIn("test", scheduler._pending_sent)
            self.assertTrue(timers)
            saved.async_save = original
            await scheduler._deliver("test")
            self.assertEqual(len(hass.services.calls), 1)
            self.assertEqual(saved.saves, 1)
            self.assertNotIn("test", scheduler._pending_sent)
        asyncio.run(run())

    def test_async_stop_waits_for_inflight_notification_and_persistence(self):
        async def run():
            scheduler, saved, hass = self._make()
            entered = asyncio.Event()
            release = asyncio.Event()
            async def notify(*args, **kwargs):
                entered.set()
                await release.wait()
            hass.services.async_call = notify
            scheduler.reschedule()
            timers[0]["callback"](datetime.now(timezone.utc))
            await entered.wait()
            stop = asyncio.create_task(scheduler.async_stop())
            await asyncio.sleep(0)
            self.assertFalse(stop.done())
            release.set()
            await stop
            self.assertTrue(saved.reminders[0]["sent"])
            self.assertEqual(saved.saves, 1)
            self.assertTrue(all(timer["cancelled"] for timer in timers))
        asyncio.run(run())

    def test_notification_ids_do_not_collide_after_sanitizing(self):
        async def run():
            scheduler, saved, hass = self._make()
            saved.reminders[0]["id"] = "a-b"
            await scheduler._deliver("a-b")
            saved.reminders[0].update(id="a_b", sent=False)
            await scheduler._deliver("a_b")
            ids = [call[2]["notification_id"] for call in hass.services.calls]
            self.assertEqual(len(set(ids)), 2)
        asyncio.run(run())

    def test_stop_cancels_timers_and_cannot_be_rearmed(self):
        scheduler, saved, hass = self._make()
        scheduler.reschedule()
        initial = len(timers)
        self.assertGreaterEqual(initial, 1)
        scheduler.stop()
        self.assertTrue(timers[0]["cancelled"])
        scheduler.reschedule()
        self.assertEqual(len(timers), initial)
        asyncio.run(scheduler._deliver("test"))
        self.assertEqual(hass.services.calls, [])

    def test_expiry_updates_saved_lists_without_notification_or_polling(self):
        async def run():
            scheduler, saved, hass = self._make()
            saved.bookmarks = []
            now = datetime.now(timezone.utc)
            saved.reminders[0].update(start=(now-timedelta(hours=1)).isoformat(),end=(now-timedelta(minutes=1)).isoformat())
            async def prune():
                saved.saves += 1
                saved.reminders = [item for item in saved.reminders if datetime.fromisoformat(item["end"])>datetime.now(timezone.utc)]
            saved.async_save = prune
            scheduler.reschedule()
            self.assertEqual(len(timers),1)
            timers[0]["callback"](now)
            await asyncio.sleep(0)
            self.assertEqual(saved.reminders,[])
            self.assertEqual(saved.saves,1)
            self.assertEqual(hass.services.calls,[])
        asyncio.run(run())

    def test_cleanup_failure_restores_memory_and_retries_storage(self):
        async def run():
            scheduler, saved, hass = self._make()
            saved.bookmarks = []
            original = [dict(item) for item in saved.reminders]
            async def fail():
                saved.reminders = []
                raise OSError("storage unavailable")
            saved.async_save = fail
            await scheduler._cleanup()
            self.assertEqual(saved.reminders,original)
            self.assertTrue(timers)
            self.assertEqual(hass.services.calls,[])
        asyncio.run(run())

    def test_success_marks_sent_once(self):
        async def run():
            scheduler, saved, hass = self._make()
            await scheduler._deliver("test")
            await scheduler._deliver("test")
            self.assertEqual(len(hass.services.calls), 1)
            self.assertTrue(saved.reminders[0]["sent"])
            self.assertEqual(saved.saves, 1)
        asyncio.run(run())

    def test_notify_destination_uses_notify_service(self):
        async def run():
            scheduler, saved, hass = self._make()
            scheduler.notification_service = "notify.mobile_app_test"
            await scheduler._deliver("test")
            self.assertEqual(len(hass.services.calls), 1)
            domain, service, payload, blocking = hass.services.calls[0]
            self.assertEqual((domain, service), ("notify", "mobile_app_test"))
            self.assertNotIn("notification_id", payload)
            self.assertTrue(blocking)
        asyncio.run(run())

    def test_cancelled_timer_callback_does_not_queue_task(self):
        scheduler, saved, hass = self._make()
        queued = []
        hass.async_create_task = lambda coro: queued.append(coro)
        scheduler.reschedule()
        callback = timers[0]["callback"]
        scheduler.stop()
        callback(datetime.now(timezone.utc))
        self.assertEqual(queued, [])

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
