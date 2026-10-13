"""Native TV Guide: EPG integration and optional add-on migration bridge."""

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
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
    try:
        url = effective_feed(options)
        if url:
            coordinator = TVGuideEPGCoordinator(hass, url, options.get("country", ""))
            await coordinator.async_config_entry_first_refresh()

        saved = TVGuideSavedProgrammes(hass, entry.entry_id)
        await saved.async_load()
        if coordinator is not None:
            hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
        hass.data.setdefault(DOMAIN + "_saved", {})[entry.entry_id] = saved
        scheduler = TVGuideReminderScheduler(
            hass, saved, hass.data.setdefault(DOMAIN + "_saved_lock", asyncio.Lock())
        )
        hass.data.setdefault(DOMAIN + "_reminder_schedulers", {})[entry.entry_id] = scheduler

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        if not hass.services.has_service(DOMAIN, "save_bookmark"):
            await async_register_saved_services(hass)
        if coordinator is not None and not hass.services.has_service(DOMAIN, "get_programmes"):
            async_register_epg_query(hass)
        scheduler.reschedule()
    except Exception:
        if scheduler is not None:
            scheduler.stop()
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        hass.data.get(DOMAIN + "_saved", {}).pop(entry.entry_id, None)
        hass.data.get(DOMAIN + "_reminder_schedulers", {}).pop(entry.entry_id, None)
        if not hass.data.get(DOMAIN + "_saved"):
            async_remove_saved_services(hass)
        if not hass.data.get(DOMAIN):
            async_remove_epg_query(hass)
        _LOGGER.exception("TV Guide setup failed")
        raise

    entry.async_on_unload(entry.add_update_listener(async_update_options))
    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Avoid needless EPG redownloads when only the sender order changes."""
    options = {**entry.data, **entry.options}
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    expected_url = effective_feed(options)
    if coordinator is not None and coordinator.url == expected_url and coordinator.country == options.get("country", ""):
        return
    if coordinator is None and not expected_url:
        return
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Release native resources after platforms unload."""
    success = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if success:
        entry.async_unload_callbacks()
        scheduler = hass.data.get(DOMAIN + "_reminder_schedulers", {}).pop(entry.entry_id, None)
        if scheduler is not None:
            scheduler.stop()
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        hass.data.get(DOMAIN + "_saved", {}).pop(entry.entry_id, None)
        if not hass.data.get(DOMAIN + "_saved"):
            async_remove_saved_services(hass)
        if not hass.data.get(DOMAIN):
            async_remove_epg_query(hass)
    return success
