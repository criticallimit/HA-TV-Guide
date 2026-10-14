"""Native TV Guide: EPG integration and optional add-on migration bridge."""

import asyncio
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .frontend import async_register_frontend
from .ui_services import async_register_ui_services, async_remove_ui_services
from .coordinator import TVGuideEPGCoordinator
from .epg_query import async_register_epg_query, async_remove_epg_query
from .country_sources import effective_feed
from .reminder_scheduler import TVGuideReminderScheduler
from .saved_programmes import TVGuideSavedProgrammes
from .saved_services import async_register_saved_services, async_remove_saved_services

_LOGGER = logging.getLogger(__name__)
PLATFORMS = (Platform.SENSOR, Platform.BINARY_SENSOR, Platform.CALENDAR)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the integration and roll back local resources on setup failures."""
    options = {**entry.data, **entry.options}
    coordinator = None
    saved = None
    scheduler = None
    platforms_started = False
    try:
        url = effective_feed(options)
        if url:
            coordinator = TVGuideEPGCoordinator(hass, url, options.get("country", ""))
            coordinator.update_interval = timedelta(minutes=options.get("refresh_minutes",180))
            await coordinator.async_config_entry_first_refresh()

        saved = TVGuideSavedProgrammes(hass, entry.entry_id)
        await saved.async_load()
        if coordinator is not None:
            hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
        hass.data.setdefault(DOMAIN + "_saved", {})[entry.entry_id] = saved
        scheduler = TVGuideReminderScheduler(
            hass, saved, hass.data.setdefault(DOMAIN + "_saved_lock", asyncio.Lock()),
            options.get("notification_service", "persistent_notification.create")
        )
        hass.data.setdefault(DOMAIN + "_reminder_schedulers", {})[entry.entry_id] = scheduler

        await async_register_frontend(hass)
        platforms_started = True
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        if not hass.services.has_service(DOMAIN, "save_bookmark"):
            await async_register_saved_services(hass)
        if coordinator is not None and not hass.services.has_service(DOMAIN, "get_programmes"):
            async_register_epg_query(hass)
        async_register_ui_services(hass)
        scheduler.reschedule()
        entry.async_on_unload(entry.add_update_listener(async_update_options))
    except (Exception, asyncio.CancelledError):
        if scheduler is not None:
            await scheduler.async_stop()
        if platforms_started:
            try:
                await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
            except Exception:
                _LOGGER.exception("TV Guide failed to roll back platforms")
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        hass.data.get(DOMAIN + "_saved", {}).pop(entry.entry_id, None)
        hass.data.get(DOMAIN + "_reminder_schedulers", {}).pop(entry.entry_id, None)
        if not hass.data.get(DOMAIN + "_saved"):
            async_remove_saved_services(hass)
            async_remove_ui_services(hass)
        if not hass.data.get(DOMAIN):
            async_remove_epg_query(hass)
        _LOGGER.exception("TV Guide setup failed")
        raise

    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Avoid needless EPG redownloads when only the sender order changes."""
    options = {**entry.data, **entry.options}
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    expected_url = effective_feed(options)
    if coordinator is not None and coordinator.url == expected_url and coordinator.country == options.get("country", "") and coordinator.update_interval == timedelta(minutes=options.get("refresh_minutes",180)):
        coordinator.async_update_listeners()
        scheduler = hass.data.get(DOMAIN + "_reminder_schedulers", {}).get(entry.entry_id)
        if scheduler is not None:
            scheduler.notification_service = options.get("notification_service", "persistent_notification.create")
        return
    if coordinator is None and not expected_url:
        scheduler = hass.data.get(DOMAIN + "_reminder_schedulers", {}).get(entry.entry_id)
        if scheduler is not None:
            scheduler.notification_service = options.get("notification_service", "persistent_notification.create")
        return
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Release native resources after platforms unload."""
    success = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if success:
        scheduler = hass.data.get(DOMAIN + "_reminder_schedulers", {}).pop(entry.entry_id, None)
        if scheduler is not None:
            await scheduler.async_stop()
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        hass.data.get(DOMAIN + "_saved", {}).pop(entry.entry_id, None)
        if not hass.data.get(DOMAIN + "_saved"):
            async_remove_saved_services(hass)
            async_remove_ui_services(hass)
        if not hass.data.get(DOMAIN):
            async_remove_epg_query(hass)
    return success
