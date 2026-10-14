"""HA lifecycle adapter for the full original multi-provider programme engine."""
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from homeassistant.const import EVENT_HOMEASSISTANT_STOP

from .coordinator import TVGuideEPGCoordinator
from .original_runtime import OriginalRuntime


class TVGuideOriginalCoordinator(TVGuideEPGCoordinator):
    """Start with cached/empty channels, then fetch sources in tracked workers."""

    is_original = True

    def __init__(self, hass, entry, options):
        super().__init__(hass, "original-providers", options.get("country") or "de", config_entry=entry)
        self.entry = entry
        self.options = options
        self.backend = None
        self._closed = False
        self._sync_pending = False
        self._loop = asyncio.get_running_loop()
        entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self.async_stop))

    def _wake(self):
        self._loop.call_soon_threadsafe(self._schedule_sync)

    def _schedule_sync(self):
        if self._closed or self._sync_pending or self.backend is None:
            return
        self._sync_pending = True
        self.hass.async_create_task(self._async_sync())

    async def _async_sync(self):
        try:
            records = await self._snapshot()
            if not self._closed:
                self.async_set_updated_data(records)
        finally:
            self._sync_pending = False

    async def _snapshot(self):
        records, catalogue, channels = await self.hass.async_add_executor_job(self.backend.snapshot)
        store = self.backend.runtime.STORE
        self.country = store.country
        self.canonical_channels, self.channels = catalogue, channels
        self.refresh_running = any(item.refresh_running for item in self.backend.runtime.COUNTRY_STORES.values())
        self.source_attempts = list(store.source_metrics)
        self.active_source = "multi-source"
        if store.last_loaded:
            self.last_successful_refresh = datetime.fromisoformat(store.last_loaded)
        self.update_interval = timedelta(minutes=store.options.get("refresh_minutes", 180))
        self._notify_refresh()
        return records

    async def _async_update_data(self):
        if self.backend is None:
            locale = {"language": self.hass.config.language, "country": self.hass.config.country,
                      "time_zone": self.hass.config.time_zone}
            storage = Path(self.hass.config.path(".storage", "tv_guide_native", self.entry.entry_id))
            self.backend = await self.hass.async_add_executor_job(OriginalRuntime, storage, self.options, locale, self._wake)
            # Setup must not wait for all broadcaster endpoints to finish.
            await self.hass.async_add_executor_job(self.backend.runtime.STORE.ensure_fresh_async)
        else:
            await self.hass.async_add_executor_job(self.backend.runtime.STORE.refresh)
        return await self._snapshot()

    async def async_original_request(self, endpoint, method="GET", body=None):
        if self._closed:
            raise RuntimeError("TV Guide is unloading")
        result = await self.hass.async_add_executor_job(self.backend.request, endpoint, method, body)
        await self._async_sync()
        return result

    async def async_stop(self, event=None):
        self._closed = True
        if self.backend is not None:
            await self.hass.async_add_executor_job(self.backend.close)
