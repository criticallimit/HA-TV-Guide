"""Refresh status from the TV Guide programme coordinator."""

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import callback

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    """Register the TV Guide refresh entity."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    entities = [TVGuideRefreshSensor(coordinator)] if coordinator is not None else []
    async_add_entities(entities)


class TVGuideRefreshSensor(BinarySensorEntity):
    """Reflect the integration's own download/parse lifecycle."""

    _attr_name = "TV Guide EPG refresh running"
    _attr_unique_id = "tv_guide_refresh_running"
    _attr_icon = "mdi:sync"
    _attr_should_poll = False

    def __init__(self, coordinator):
        self._coordinator = coordinator

    @property
    def is_on(self):
        return self._coordinator.refresh_running

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.async_on_remove(self._coordinator.subscribe_refresh(self._refresh_changed))

    @callback
    def _refresh_changed(self):
        self.async_write_ha_state()
