"""HA lifecycle adapter for the multi-provider programme engine."""
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN
from .coordinator import TVGuideEPGCoordinator
from .guide_runtime import GuideRuntime


class TVGuideCoordinator(TVGuideEPGCoordinator):
    """Start with cached/empty channels, then fetch sources in tracked workers."""

    is_multi_source = True

    def __init__(self, hass, entry, options):
        super().__init__(hass, "multi-source-providers", options.get("country") or "de", config_entry=entry)
        self.entry = entry
        self.options = options
        self.backend = None
        self._closed = False
        self._stop_task = None
        self._startup_task = None
        self._sync_pending = False
        self._sync_requested = False
        self._sync_lock = asyncio.Lock()
        self._last_refresh_notification = None
        self._cancel_preload = None
        self._loop = asyncio.get_running_loop()
        entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._async_stop_on_shutdown))

    def _wake(self):
        if not self._closed:
            self._loop.call_soon_threadsafe(self._schedule_sync)

    def _schedule_sync(self):
        if self._closed or self.backend is None:
            return
        self._sync_requested = True
        if self._sync_pending:
            return
        self._sync_pending = True
        self.hass.async_create_task(self._async_sync())

    async def _async_sync(self):
        async with self._sync_lock:
            try:
                while not self._closed:
                    self._sync_requested = False
                    records = await self._snapshot()
                    if not self._closed:
                        self.async_set_updated_data(records)
                    if not self._sync_requested:
                        break
            finally:
                self._sync_pending = False

    async def _snapshot(self):
        records, catalogue, channels, status = await self.hass.async_add_executor_job(self.backend.state_snapshot)
        self.country = status['country']
        self.canonical_channels, self.channels = catalogue, channels
        self.refresh_running = status['refresh_running']
        self.source_attempts = status['source_attempts']
        self.active_source = "multi-source"
        try:
            loaded = datetime.fromisoformat(status['last_loaded']) if status['last_loaded'] else None
            if loaded is not None and loaded.tzinfo is not None:
                loaded.astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError):
            loaded = None
        self.last_successful_refresh = loaded if loaded is not None and loaded.tzinfo is not None else None
        self.update_interval = timedelta(minutes=status['refresh_minutes'])
        notification = (self.country, self.refresh_running, self.last_successful_refresh)
        if notification != self._last_refresh_notification:
            self._last_refresh_notification = notification
            self._notify_refresh()
        return records

    async def _async_update_data(self):
        if self._closed:
            raise RuntimeError("TV Guide is unloading")
        if self.backend is None:
            if self._startup_task is None:
                self._startup_task = asyncio.create_task(self._async_start_backend())
            # Cancelling setup cannot cancel the executor's constructor. Retain
            # ownership until its result can be closed by async_stop instead.
            await asyncio.shield(self._startup_task)
        else:
            await self.hass.async_add_executor_job(self.backend.refresh_active)
        if self._closed:
            raise RuntimeError("TV Guide is unloading")
        return await self._snapshot()

    async def _async_start_backend(self):
        locale = {"language": self.hass.config.language, "country": self.hass.config.country,
                  "time_zone": self.hass.config.time_zone}
        storage = Path(self.hass.config.path(".storage", "tv_guide_store", self.entry.entry_id))
        self.backend = await self.hass.async_add_executor_job(GuideRuntime, storage, self.options, locale, self._wake)
        if self._closed:
            return
        # Setup must not wait for all broadcaster endpoints to finish.
        await self.hass.async_add_executor_job(self.backend.runtime.STORE.ensure_fresh_async)
        if not self._closed:
            await self.hass.async_add_executor_job(self.backend.start_logo_download)
        if not self._closed:
            self._cancel_preload = async_track_time_interval(self.hass, self._async_preload, timedelta(minutes=5))

    async def _async_preload(self, _now):
        if not self._closed and self.backend is not None:
            await self.hass.async_add_executor_job(self.backend.maintain_caches)

    async def async_guide_request(self, endpoint, method="GET", body=None):
        if self._closed:
            raise RuntimeError("TV Guide is unloading")
        result = await self.hass.async_add_executor_job(self.backend.request, endpoint, method, body)
        # Pure reads must not rebuild the entire HA coordinator snapshot before
        # the already prepared EPG response reaches the frontend. Provider
        # refreshes still notify through _wake; writes retain synchronous updates.
        if method != "GET" or endpoint == "refresh":
            await self._async_sync()
        return result

    async def _async_stop_on_shutdown(self, event):
        # Shutdown can arrive independently of config-entry unload.
        async with self.hass.data.setdefault(DOMAIN + "_settings_lock", asyncio.Lock()):
            await self.async_stop(event)

    async def async_stop(self, event=None):
        """Wait for the same cleanup when unload and shutdown overlap."""
        if self._stop_task is None:
            self._closed = True
            self._stop_task = asyncio.create_task(self._async_close_resources())
        await asyncio.shield(self._stop_task)

    async def _async_close_resources(self):
        if self._startup_task is not None:
            await asyncio.gather(asyncio.shield(self._startup_task), return_exceptions=True)
        if self._cancel_preload is not None:
            self._cancel_preload()
            self._cancel_preload = None
        if self.backend is not None:
            await self.hass.async_add_executor_job(self.backend.close)
