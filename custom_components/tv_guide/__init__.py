"""TV Guide native entity bridge.

Temporary migration mode: mirror only states explicitly owned by the add-on.
No external EPG/network polling takes place here.
"""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

PLATFORMS = (Platform.SENSOR, Platform.BINARY_SENSOR)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Register the native bridge platforms."""
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the native bridge platforms."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
