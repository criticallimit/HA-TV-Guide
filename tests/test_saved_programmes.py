"""Offline tests for add-on-compatible bookmarks/reminders validation."""

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "tv_guide"
PACKAGE = "_tvguide_saved_tests"
pkg = types.ModuleType(PACKAGE)
pkg.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = pkg

# Home Assistant Store is only needed when instantiated; stub for pure validation tests.
homeassistant = types.ModuleType("homeassistant")
homeassistant.__path__ = []
helpers = types.ModuleType("homeassistant.helpers")
helpers.__path__ = []
storage = types.ModuleType("homeassistant.helpers.storage")
storage.Store = type("Store", (), {})
sys.modules.setdefault("homeassistant", homeassistant)
sys.modules.setdefault("homeassistant.helpers", helpers)
sys.modules.setdefault("homeassistant.helpers.storage", storage)

spec = importlib.util.spec_from_file_location(f"{PACKAGE}.saved_programmes", ROOT / "saved_programmes.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class SavedProgrammeTests(unittest.TestCase):
    def test_long_country_qualified_channel_id_survives_storage(self):
        now=datetime.now(timezone.utc)+timedelta(hours=1)
        channel_id='de:'+'x'*160
        item={'id':'long','channelId':channel_id,'start':now.isoformat(),'end':(now+timedelta(hours=1)).isoformat()}
        self.assertEqual(module.normalize_items([item])[0]['channelId'],channel_id)

    def test_minute_selector_strings_are_supported_but_fractional_values_are_rejected(self):
        for value in (5,10,15,30,'5','10','15','30'):
            self.assertEqual(module.normalize_reminder_minutes(value),int(value))
        for value in (True,10.5,10.0,'10.5','11',None):
            with self.assertRaises(ValueError):module.normalize_reminder_minutes(value)

    def test_original_field_names_and_deduplication(self):
        now = datetime.now(timezone.utc)
        base = {
            "id": "one", "title": "Film", "channel": "ARD",
            "channelId": "ard",
            "start": (now + timedelta(hours=1)).isoformat(),
            "end": (now + timedelta(hours=2)).isoformat(),
        }
        self.assertEqual(module.normalize_items([base, base]), [base])
        reminders = module.normalize_items([{**base, "minutes": 15, "sent": False}], reminders=True)
        self.assertEqual(reminders[0]["minutes"], 15)
        self.assertEqual(reminders[0]["channelId"], "ard")

    def test_storage_change_subscription(self):
        class FakeStore:
            def __init__(self):
                self.writes = []
            async def async_save(self, data):
                self.writes.append(data)

        async def run():
            saved = module.TVGuideSavedProgrammes.__new__(module.TVGuideSavedProgrammes)
            saved._store = FakeStore()
            saved.bookmarks = []
            saved.reminders = []
            saved._subscribers = set()
            events = []
            callback = lambda: events.append("changed")
            saved.subscribe(callback)
            await saved.async_save()
            self.assertEqual(events, ["changed"])
            saved.unsubscribe(callback)
            await saved.async_save()
            self.assertEqual(events, ["changed"])
            self.assertEqual(len(saved._store.writes), 2)

        import asyncio
        asyncio.run(run())

    def test_saved_records_sort_by_instant_across_timezone_offsets(self):
        now = datetime.now(timezone.utc) + timedelta(days=1)
        early = {"id":"early","start":now.astimezone(timezone(timedelta(hours=3))).isoformat(),"end":(now+timedelta(hours=2)).isoformat()}
        late = {"id":"late","start":(now+timedelta(hours=1)).isoformat(),"end":(now+timedelta(hours=2)).isoformat()}
        self.assertEqual([item["id"] for item in module.normalize_items([late,early])], ["early","late"])

    def test_subscriber_failure_cannot_turn_successful_storage_into_failed_action(self):
        import asyncio
        async def run():
            saved=module.TVGuideSavedProgrammes.__new__(module.TVGuideSavedProgrammes)
            events=[]
            class Store:
                async def async_save(self,data):events.append("committed")
            saved._store=Store();saved.bookmarks=[];saved.reminders=[];saved._subscribers=set()
            def bad():raise RuntimeError("unloaded entity")
            saved.subscribe(bad)
            saved.subscribe(lambda:events.append("other subscriber"))
            await saved.async_save()
            self.assertIn("committed",events)
            self.assertIn("other subscriber",events)
        asyncio.run(run())

    def test_expired_and_invalid_rejected(self):
        now = datetime.now(timezone.utc)
        past = {
            "id": "expired", "start": (now - timedelta(hours=2)).isoformat(),
            "end": (now - timedelta(hours=1)).isoformat()
        }
        self.assertEqual(module.normalize_items([past, {}, "wrong"]), [])
        future = {
            "id": "valid", "start": (now + timedelta(hours=1)).isoformat(),
            "end": (now + timedelta(hours=2)).isoformat()
        }
        self.assertEqual(module.normalize_items([{**future, "minutes": 3}], reminders=True), [])
        self.assertEqual(module.normalize_items([{**future, "minutes": 10}], reminders=True)[0]["minutes"], 10)


if __name__ == "__main__":
    unittest.main()
