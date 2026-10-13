"""Native refresh-in-progress indicator for the TV Guide add-on bridge."""

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_state_change_event

from .const import DOMAIN, REFRESH_SOURCE, SOURCE
from .state_values import owned_state


async def async_setup_entry(hass, entry, async_add_entities):
    """Register one native bridge binary sensor."""
    async_add_entities([TVGuideRefreshSensor()])


class TVGuideRefreshSensor(BinarySensorEntity):
    """Mirror only the state published by the existing add-on."""

    _attr_name = "TV Guide Native EPG refresh running"
    _attr_unique_id = f"{DOMAIN}_bridge_refresh_running"
    _attr_icon = "mdi:sync"
    _attr_should_poll = False

    def __init__(self):
        self._state = None

    @property
    def available(self):
        return self._state is not None

    @property
    def is_on(self):
        return self._state == "on"

    @callback
    def _update(self):
        state = self.hass.states.get(REFRESH_SOURCE)
        self._state = state.state if state is not None and owned_state(state.attributes, SOURCE) and state.state in ("on", "off") else None
        self.async_write_ha_state()

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        @callback
        def on_change(event):
            self._update()
        self.async_on_remove(
            async_track_state_change_event(self.hass, [REFRESH_SOURCE], on_change)
        )
        self._update()
