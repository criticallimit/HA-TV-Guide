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
