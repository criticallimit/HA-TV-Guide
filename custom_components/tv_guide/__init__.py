"""Native TV Guide: optional EPG feed and add-on migration bridge."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import TVGuideEPGCoordinator
from .saved_programmes import TVGuideSavedProgrammes
from .saved_services import async_register_saved_services, async_remove_saved_services
from .reminder_scheduler import TVGuideReminderScheduler
import asyncio
from .country_sources import effective_feed

PLATFORMS = (Platform.SENSOR, Platform.BINARY_SENSOR, Platform.CALENDAR)
CONF_FEED_URL = "feed_url"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up native entities with one coordinator per configured feed."""
    options = {**entry.data, **entry.options}
    url = effective_feed(options)
    coordinator = None
    if url:
        coordinator = TVGuideEPGCoordinator(hass, url, options.get("country", ""))
        await coordinator.async_config_entry_first_refresh()
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    saved = TVGuideSavedProgrammes(hass, entry.entry_id)
    await saved.async_load()
    hass.data.setdefault(DOMAIN + "_saved", {})[entry.entry_id] = saved
    scheduler = TVGuideReminderScheduler(
        hass, saved, hass.data.setdefault(DOMAIN + "_saved_lock", asyncio.Lock())
    )
    hass.data.setdefault(DOMAIN + "_reminder_schedulers", {})[entry.entry_id] = scheduler
    scheduler.reschedule()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    if not hass.services.has_service(DOMAIN, "save_bookmark"):
        await async_register_saved_services(hass)
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload after XMLTV feed settings change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload entities and release coordinator reference."""
    success = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if success:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        scheduler = hass.data.get(DOMAIN + "_reminder_schedulers", {}).pop(entry.entry_id, None)
        if scheduler is not None:
            scheduler.stop()
        hass.data.get(DOMAIN + "_saved", {}).pop(entry.entry_id, None)
        if not hass.data.get(DOMAIN + "_saved"):
            async_remove_saved_services(hass)
    return success
