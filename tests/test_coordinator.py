"""Offline refresh tests with real XML parsing and isolated HA/network doubles."""
import asyncio
from contextlib import asynccontextmanager
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "tv_guide"
PKG = "_tvguide_coordinator_tests"
FUTURE = b'<tv><channel id="zdf"><display-name>ZDF</display-name></channel><programme channel="zdf" start="20990101000000 +0000" stop="20990101010000 +0000"><title>News</title></programme></tv>'
EXPIRED = FUTURE.replace(b"2099", b"2000")


class UpdateFailed(Exception):
    pass


class CoordinatorBase:
    @classmethod
    def __class_getitem__(cls, item):
        return cls

    def __init__(self, hass, **kwargs):
        self.hass = hass


class CoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        imports = {}
        package = types.ModuleType(PKG)
        package.__path__ = [str(ROOT)]
        imports[PKG] = package

        def stub(name, **values):
            module = types.ModuleType(name)
            module.__dict__.update(values)
            imports[name] = module

        stub("homeassistant.helpers.update_coordinator", DataUpdateCoordinator=CoordinatorBase, UpdateFailed=UpdateFailed)
        self.calls = []
        self.responses = {}
        self.sessions_closed = 0

        @asynccontextmanager
        async def session():
            try:
                yield object()
            finally:
                self.sessions_closed += 1

        async def fetch(session, url):
            self.calls.append(url)
            result = self.responses[url]
            if isinstance(result, BaseException):
                raise result
            return result

        stub(PKG + ".secure_transport", public_epg_session=session)
        stub(PKG + ".epg_client", fetch_programmes=fetch, decompress_feed=lambda payload: payload)
        stub(PKG + ".catalogs", resolve_catalogue_channels=lambda country, channels: [{"id": "canonical", "available": True}])
        async def executor(fn, *args):
            return fn(*args)
        hass = types.SimpleNamespace(async_add_executor_job=executor)
        spec = importlib.util.spec_from_file_location(PKG + ".coordinator", ROOT / "coordinator.py")
        module = importlib.util.module_from_spec(spec)
        # Retain isolated imports during tests so real parser/catalog modules resolve.
        self.import_patch = patch.dict(sys.modules, imports)
        self.import_patch.start()
        self.addCleanup(self.import_patch.stop)
        spec.loader.exec_module(module)
        self.coordinator = module.TVGuideEPGCoordinator(hass, "primary", "de", ("primary", "fallback"))
        self.busy = []
        self.coordinator.subscribe_refresh(lambda: self.busy.append(self.coordinator.refresh_running))

    async def test_primary_success_does_not_download_fallback(self):
        self.responses = {"primary": FUTURE}
        result = await self.coordinator._async_update_data()
        self.assertEqual(result[0]["title"], "News")
        self.assertEqual(self.calls, ["primary"])
        self.assertEqual(self.coordinator.active_source, "primary")
        self.assertEqual(self.coordinator.channels[0]["id"], "zdf")
        self.assertEqual(self.busy, [True, False])

    async def test_transport_malformed_empty_and_expired_feed_use_fallback(self):
        for response in (ConnectionError("offline"), b"<broken", b"<tv/>", EXPIRED):
            with self.subTest(response=response):
                self.calls.clear()
                self.responses = {"primary": response, "fallback": FUTURE}
                result = await self.coordinator._async_update_data()
                self.assertEqual(len(result), 1)
                self.assertEqual(self.calls, ["primary", "fallback"])
                self.assertEqual(self.coordinator.active_source, "fallback")
                self.assertEqual(self.coordinator.url, "primary")
                self.assertEqual(self.coordinator.source_attempts[-1]["result"], "success")

    async def test_all_fail_preserves_successful_snapshot_metadata(self):
        self.responses = {"primary": FUTURE}
        await self.coordinator._async_update_data()
        previous = (self.coordinator.channels, self.coordinator.canonical_channels, self.coordinator.last_successful_refresh)
        self.responses = {"primary": EXPIRED, "fallback": ConnectionError("offline")}
        with self.assertRaises(UpdateFailed):
            await self.coordinator._async_update_data()
        self.assertEqual(previous, (self.coordinator.channels, self.coordinator.canonical_channels, self.coordinator.last_successful_refresh))
        self.assertEqual(self.coordinator.active_source, "primary")
        self.assertEqual(len(self.coordinator.source_attempts), 2)
        self.assertFalse(self.coordinator.refresh_running)

    async def test_each_refresh_retries_primary_after_fallback(self):
        self.responses = {"primary": EXPIRED, "fallback": FUTURE}
        await self.coordinator._async_update_data()
        self.calls.clear()
        self.responses["primary"] = FUTURE
        await self.coordinator._async_update_data()
        self.assertEqual(self.calls, ["primary"])
        self.assertEqual(self.coordinator.active_source, "primary")

    async def test_single_custom_feed_never_contacts_country_fallback(self):
        self.coordinator.source_urls = ("primary",)
        self.responses = {"primary": ConnectionError("offline")}
        with self.assertRaises(UpdateFailed):
            await self.coordinator._async_update_data()
        self.assertEqual(self.calls, ["primary"])

    async def test_cancellation_closes_session_without_fallback(self):
        self.responses = {"primary": asyncio.CancelledError()}
        with self.assertRaises(asyncio.CancelledError):
            await self.coordinator._async_update_data()
        self.assertEqual(self.calls, ["primary"])
        self.assertEqual(self.sessions_closed, 1)
        self.assertFalse(self.coordinator.refresh_running)


if __name__ == "__main__":
    unittest.main()
