"""TV Guide saved-list action adapter tests with isolated HA service/store doubles."""
import asyncio
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "tv_guide"
PKG = "_tvguide_saved_service_tests"
pkg = types.ModuleType(PKG)
pkg.__path__ = [str(ROOT)]
vol = types.ModuleType("voluptuous")
vol.Required = vol.Optional = lambda key, **kwargs: key
vol.Schema = lambda value: value
vol.All = lambda *args: args
vol.Length = lambda **kwargs: kwargs
vol.In = lambda values: values
core = types.ModuleType("homeassistant.core")
core.SupportsResponse = types.SimpleNamespace(ONLY="only")
exc = types.ModuleType("homeassistant.exceptions")
exc.HomeAssistantError = type("HomeAssistantError", (Exception,), {})
storage = types.ModuleType("homeassistant.helpers.storage")
storage.Store = type("Store", (), {})
with patch.dict(sys.modules, {PKG:pkg, "voluptuous":vol, "homeassistant.core":core, "homeassistant.exceptions":exc, "homeassistant.helpers.storage":storage}):
    for name in ("const", "saved_programmes", "saved_services"):
        spec = importlib.util.spec_from_file_location(f"{PKG}.{name}", ROOT / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
services_module = module

class Registry:
    def __init__(self):
        self.handlers = {}
        self.response = {}
    def async_register(self, domain, name, handler, **kwargs):
        self.handlers[name] = handler
        self.response[name] = kwargs.get("supports_response")
    def async_remove(self, domain, name):
        self.handlers.pop(name, None)

class Saved:
    def __init__(self):
        self.bookmarks = []
        self.reminders = []
        self.saves = 0
        self.fail = False
    async def async_save(self):
        if self.fail:
            raise OSError("Storage unavailable")
        self.saves += 1

class SavedServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.saved = Saved()
        self.hass = types.SimpleNamespace(data={"tv_guide_saved":{"entry":self.saved}}, services=Registry(), config=types.SimpleNamespace(language="de"))
        await services_module.async_register_saved_services(self.hass)
        now = datetime.now(timezone.utc)
        self.record = {"id":"guide_test", "title":"Film", "channel":"Das Erste", "channel_id":"DasErste.de", "start":(now+timedelta(hours=1)).isoformat(), "end":(now+timedelta(hours=2)).isoformat()}

    async def call(self, name, data=None):
        return await self.hass.services.handlers[name](types.SimpleNamespace(service=name, data=data or {}))

    async def test_save_read_remove_roundtrip_and_response_registration(self):
        await self.call("save_bookmark", self.record)
        await self.call("save_reminder", {**self.record,"minutes":15})
        response = await self.call("get_saved_programmes")
        self.assertEqual(response["bookmarks"][0]["channelId"], "DasErste.de")
        self.assertFalse(response["reminders"][0]["sent"])
        self.assertEqual(response["reminders"][0]["minutes"], 15)
        self.assertEqual(self.saved.saves, 2)
        self.assertEqual(self.hass.services.response["get_saved_programmes"], "only")
        await self.call("remove_saved_programme", {"id":"guide_test","kind":"bookmark"})
        self.assertEqual((await self.call("get_saved_programmes"))["bookmarks"], [])
        self.assertEqual(len(self.saved.reminders), 1)
        services_module.async_remove_saved_services(self.hass)
        self.assertEqual(self.hass.services.handlers, {})

    async def test_bookmark_and_reminder_preserve_long_channel_identifiers(self):
        record={**self.record,'channel_id':'at:'+'x'*160}
        await self.call('save_bookmark',record)
        await self.call('save_reminder',{**record,'minutes':'15'})
        result=await self.call('get_saved_programmes')
        self.assertEqual(result['bookmarks'][0]['channelId'],record['channel_id'])
        self.assertEqual(result['reminders'][0]['channelId'],record['channel_id'])
        self.assertEqual(result['reminders'][0]['minutes'],15)

    async def test_read_omits_expired_records_and_returns_independent_snapshot(self):
        await self.call("save_bookmark", self.record)
        old = datetime.now(timezone.utc)-timedelta(days=1)
        self.saved.bookmarks.append({**self.saved.bookmarks[0],"id":"expired","start":old.isoformat(),"end":(old+timedelta(hours=1)).isoformat()})
        response = await self.call("get_saved_programmes")
        self.assertEqual(len(response["bookmarks"]), 1)
        response["bookmarks"][0]["title"] = "Changed"
        self.assertEqual(self.saved.bookmarks[0]["title"], "Film")
        self.assertEqual(len(self.saved.bookmarks), 2)
        self.assertEqual(self.saved.saves, 1)

    async def test_storage_failure_does_not_leave_phantom_bookmark(self):
        self.saved.fail = True
        with self.assertRaises(OSError):
            await self.call("save_bookmark", self.record)
        self.assertEqual(self.saved.bookmarks, [])

    async def test_full_list_rejects_new_item_but_allows_replacement(self):
        await self.call("save_bookmark", self.record)
        template = self.saved.bookmarks[0]
        self.saved.bookmarks = [{**template,"id":str(i)} for i in range(1000)]
        with self.assertRaises(exc.HomeAssistantError):
            await self.call("save_bookmark", self.record)
        self.assertEqual(len(self.saved.bookmarks), 1000)
        await self.call("save_bookmark", {**self.record,"id":"0","title":"Replacement"})
        self.assertEqual(len(self.saved.bookmarks), 1000)
        self.assertEqual(next(item for item in self.saved.bookmarks if item["id"] == "0")["title"], "Replacement")

    async def test_remove_programme_atomically_removes_bookmark_and_reminder(self):
        await self.call("save_bookmark", self.record)
        await self.call("save_reminder", {**self.record,"minutes":10})
        self.saved.fail = True
        with self.assertRaises(OSError):
            await self.call("remove_saved_programme", {"kind":"programme","id":self.record["id"]})
        self.assertEqual(len(self.saved.bookmarks),1)
        self.assertEqual(len(self.saved.reminders),1)
        self.saved.fail = False
        await self.call("remove_saved_programme", {"kind":"programme","id":self.record["id"]})
        self.assertEqual(self.saved.bookmarks,[])
        self.assertEqual(self.saved.reminders,[])

    async def test_no_loaded_entry_reports_error(self):
        self.hass.data["tv_guide_saved"] = {}
        with self.assertRaises(exc.HomeAssistantError):
            await self.call("get_saved_programmes")

if __name__ == "__main__":
    unittest.main()
