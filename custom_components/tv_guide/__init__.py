"""Native TV Guide: optional EPG feed and add-on migration bridge."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import TVGuideEPGCoordinator

PLATFORMS = (Platform.SENSOR, Platform.BINARY_SENSOR)
CONF_FEED_URL = "feed_url"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up native entities with one coordinator per configured feed."""
    url = entry.options.get(CONF_FEED_URL, entry.data.get(CONF_FEED_URL))
    if url:
        coordinator = TVGuideEPGCoordinator(hass, url)
        await coordinator.async_config_entry_first_refresh()
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
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
    return success
