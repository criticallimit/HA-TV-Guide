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

    def test_missing_canonical_sender_not_all_programmes(self):
        programmes = [{"channel": "unknown", "start": "2026-10-13T19:00:00+00:00", "stop": "2026-10-13T20:00:00+00:00"}]
        cat = [{"id": "ard", "xmltv_id": None, "name": "Das Erste"}]
        start = datetime(2026, 10, 13, 19, 0, tzinfo=timezone.utc)
        end = datetime(2026, 10, 13, 20, 0, tzinfo=timezone.utc)
        self.assertEqual(query(programmes, cat, [], channel_id="ard", start=start, end=end, limit=10), [])


if __name__ == "__main__":
    unittest.main()
