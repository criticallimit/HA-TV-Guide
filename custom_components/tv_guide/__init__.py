"""Native TV Guide integration with optional standalone EPG retrieval."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import TVGuideEPGCoordinator

PLATFORMS = (Platform.SENSOR, Platform.BINARY_SENSOR)
CONF_FEED_URL = "feed_url"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up native entities, fetching EPG only when explicitly configured."""
    url = entry.data.get(CONF_FEED_URL)
    if url:
        coordinator = TVGuideEPGCoordinator(hass, url)
        # Report unavailable feeds as a setup failure rather than loading a
        # seemingly healthy entry without programme data.
        await coordinator.async_config_entry_first_refresh()
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload entities and release coordinator reference."""
    success = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if success:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return success
