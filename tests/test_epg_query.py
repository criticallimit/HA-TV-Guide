"""Offline test for querying the cached EPG with no network requests."""

import importlib.util
from datetime import datetime, timezone
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "tv_guide"
PKG = "_tvguide_query_tests"
package = types.ModuleType(PKG)
package.__path__ = [str(ROOT)]
sys.modules[PKG] = package

# Query logic is pure; only the service adapter imports HA and Voluptuous.
try:
    import voluptuous  # noqa: F401
except ImportError:
    voluptuous = types.ModuleType("voluptuous")
    class Optional:
        def __init__(self, *_args, **_kwargs):
            pass
    class Required(Optional):
        pass
    voluptuous.Optional = Optional
    voluptuous.Required = Required
    voluptuous.Schema = lambda value: value
    voluptuous.All = lambda *args: args
    voluptuous.Coerce = lambda value: value
    voluptuous.Range = lambda **kwargs: kwargs
    sys.modules["voluptuous"] = voluptuous

ha = types.ModuleType("homeassistant")
ha.__path__ = []
core = types.ModuleType("homeassistant.core")
core.callback = lambda func: func
core.SupportsResponse = type("SupportsResponse", (), {"ONLY": 1})
exc = types.ModuleType("homeassistant.exceptions")
exc.HomeAssistantError = type("HomeAssistantError", (Exception,), {})
sys.modules.setdefault("homeassistant", ha)
sys.modules.setdefault("homeassistant.core", core)
sys.modules.setdefault("homeassistant.exceptions", exc)

for name in ("channel_mapping", "channel_selection", "const", "epg_query"):
    spec = importlib.util.spec_from_file_location(f"{PKG}.{name}", ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
query = sys.modules[f"{PKG}.epg_query"].query_programmes
channel_payload = sys.modules[f"{PKG}.epg_query"].channel_payload


class QueryTests(unittest.TestCase):
    def test_response_action_reports_truncation_and_stable_ids(self):
        import asyncio
        import threading
        from types import SimpleNamespace
        threads = []
        async def executor(fn, *args):
            def run():
                threads.append(threading.get_ident())
                return fn(*args)
            return await asyncio.to_thread(run)
        handlers = {}
        coordinator = SimpleNamespace(
            data=[{"channel":"ard", "start":"2026-10-13T19:00:00+00:00", "stop":"2026-10-13T20:00:00+00:00", "title":str(i)} for i in range(501)],
            canonical_channels=[], channels=[], country="",
        )
        hass = SimpleNamespace(
            async_add_executor_job=executor,
            data={"tv_guide":{"entry":coordinator}},
            services=SimpleNamespace(async_register=lambda domain,name,handler,**kwargs: handlers.update({name:handler})),
            config_entries=SimpleNamespace(async_get_entry=lambda entry_id: SimpleNamespace(data={},options={})),
        )
        sys.modules[f"{PKG}.epg_query"].async_register_epg_query(hass)
        call = SimpleNamespace(data={"start":"2026-10-13T19:00:00+00:00","end":"2026-10-13T20:00:00+00:00","channel_id":"","limit":500})
        response = asyncio.run(handlers["get_programmes"](call))
        self.assertTrue(response["truncated"])
        self.assertEqual(response["count"], 500)
        self.assertEqual(len(response["programmes"]), 500)
        self.assertTrue(response["programmes"][0]["id"].startswith("native_"))
        self.assertEqual(len(threads), 1)
        self.assertNotEqual(threads[0], threading.get_ident())

    def test_stable_programme_ids_use_feed_id_and_utc_instant(self):
        make_id = sys.modules[f"{PKG}.epg_query"].programme_id
        first = make_id("DasErste.de", datetime.fromisoformat("2026-10-13T20:15:00+02:00"))
        second = make_id("DasErste.de", datetime.fromisoformat("2026-10-13T18:15:00+00:00"))
        self.assertEqual(first, second)
        self.assertNotEqual(first, make_id("ZDF.de", datetime.fromisoformat("2026-10-13T18:15:00+00:00")))
        self.assertLess(len(first), 200)

    def test_channel_catalogue_keeps_main_and_additional_stations(self):
        from types import SimpleNamespace
        coordinator = SimpleNamespace(
            country="de",
            canonical_channels=[
                {"id": "ard", "name": "Das Erste", "xmltv_id": "DasErste.de", "available": True},
                {"id": "zdf", "name": "ZDF", "xmltv_id": None, "available": False},
            ],
            channels=[
                {"id": "DasErste.de", "name": "ARD"},
                {"id": "extra.tv", "name": "Extra TV"},
            ],
        )
        response = channel_payload(coordinator, ["extra.tv", "ard"])
        self.assertEqual(response["count"], 3)
        self.assertEqual([item["id"] for item in response["channels"]], ["extra.tv", "ard", "zdf"])
        self.assertFalse(response["channels"][-1]["available"])
        self.assertFalse(response["channels"][-1]["selected"])

    def test_set_channel_helper_accepts_known_ids(self):
        from types import SimpleNamespace
        coordinator = SimpleNamespace(
            country="de",
            canonical_channels=[{"id": "ard", "name": "Das Erste", "xmltv_id": "DasErste.de", "available": True}],
            channels=[{"id": "DasErste.de", "name": "Das Erste"}],
        )
        result = channel_payload(coordinator, ["ard"])
        self.assertEqual(result["channels"][0]["selected"], True)

    def test_filter_channel_and_window(self):
        programmes = [
            {"channel": "ZDF.de", "start": "2026-10-13T19:00:00+00:00", "stop": "2026-10-13T20:00:00+00:00", "title": "ZDF"},
            {"channel": "DasErste.de", "start": "2026-10-13T19:00:00+00:00", "stop": "2026-10-13T20:00:00+00:00", "title": "ARD"},
        ]
        catalogue = [{"id": "ard", "name": "Das Erste", "xmltv_id": "DasErste.de"}]
        start = datetime(2026, 10, 13, 19, 30, tzinfo=timezone.utc)
        end = datetime(2026, 10, 13, 20, 30, tzinfo=timezone.utc)
        result = query(programmes, catalogue, [], channel_id="ard", start=start, end=end, limit=5)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "ARD")
        self.assertEqual(result[0]["channel_name"], "Das Erste")

    def test_timezone_offsets_sort_by_actual_instant(self):
        programmes = [
            {"channel": "b", "start": "2026-10-13T20:00:00+02:00", "stop": "2026-10-13T21:00:00+02:00", "title": "later"},
            {"channel": "a", "start": "2026-10-13T18:30:00+01:00", "stop": "2026-10-13T19:30:00+01:00", "title": "earlier"},
            {"channel": "bad", "start": "2026-10-13T19:00:00", "stop": "2026-10-13T20:00:00", "title": "invalid"},
        ]
        start = datetime(2026, 10, 13, 17, 0, tzinfo=timezone.utc)
        end = datetime(2026, 10, 13, 20, 0, tzinfo=timezone.utc)
        result = query(programmes, [], [], channel_id="", start=start, end=end, limit=10)
        self.assertEqual([item["title"] for item in result], ["earlier", "later"])

    def test_uses_saved_selection_when_channel_not_specified(self):
        programmes = [
            {"channel": "ard.feed", "start": "2026-10-13T19:00:00+00:00", "stop": "2026-10-13T20:00:00+00:00", "title": "ARD"},
            {"channel": "zdf.feed", "start": "2026-10-13T19:00:00+00:00", "stop": "2026-10-13T20:00:00+00:00", "title": "ZDF"},
        ]
        catalogue = [{"id": "ard", "name": "Das Erste", "xmltv_id": "ard.feed"}]
        start = datetime(2026, 10, 13, 19, 0, tzinfo=timezone.utc)
        end = datetime(2026, 10, 13, 20, 0, tzinfo=timezone.utc)
        result = query(programmes, catalogue, [], channel_id="", start=start, end=end, limit=100, selected=["ard"])
        self.assertEqual([item["title"] for item in result], ["ARD"])

    def test_explicit_channel_cannot_bypass_saved_selection(self):
        programmes = [
            {"channel": "ard.feed", "start": "2026-10-13T19:00:00+00:00", "stop": "2026-10-13T20:00:00+00:00", "title": "ARD"},
            {"channel": "zdf.feed", "start": "2026-10-13T19:00:00+00:00", "stop": "2026-10-13T20:00:00+00:00", "title": "ZDF"},
        ]
        catalogue = [
            {"id": "ard", "name": "Das Erste", "xmltv_id": "ard.feed"},
            {"id": "zdf", "name": "ZDF", "xmltv_id": "zdf.feed"},
        ]
        start = datetime(2026, 10, 13, 19, 0, tzinfo=timezone.utc)
        end = datetime(2026, 10, 13, 20, 0, tzinfo=timezone.utc)
        filtered = query(programmes, catalogue, [], channel_id="zdf", start=start, end=end, limit=100, selected=["ard"])
        self.assertEqual(filtered, [])
        allowed = query(programmes, catalogue, [], channel_id="ard", start=start, end=end, limit=100, selected=["ard"])
        self.assertEqual([item["title"] for item in allowed], ["ARD"])

    def test_missing_canonical_sender_not_all_programmes(self):
        programmes = [{"channel": "unknown", "start": "2026-10-13T19:00:00+00:00", "stop": "2026-10-13T20:00:00+00:00"}]
        cat = [{"id": "ard", "xmltv_id": None, "name": "Das Erste"}]
        start = datetime(2026, 10, 13, 19, 0, tzinfo=timezone.utc)
        end = datetime(2026, 10, 13, 20, 0, tzinfo=timezone.utc)
        self.assertEqual(query(programmes, cat, [], channel_id="ard", start=start, end=end, limit=10), [])


if __name__ == "__main__":
    unittest.main()
