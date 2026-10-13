"""Native sensors mirroring explicitly owned TV Guide add-on states.

This migration bridge does not contact EPG providers or the add-on HTTP API.
"""

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_state_change_event

from .const import DOMAIN, SENSORS, SOURCE
from .state_values import owned_state, parse_count, parse_timestamp


async def async_setup_entry(hass, entry, async_add_entities):
    """Create four read-only, registry-backed bridge sensors."""
    async_add_entities([TVGuideSensor(key, *definition) for key, definition in SENSORS.items()])


class TVGuideSensor(SensorEntity):
    """Reflect an add-on-owned state without reusing its entity ID."""

    _attr_has_entity_name = False
    _attr_should_poll = False

    def __init__(self, key, source_entity, name, icon, timestamp):
        self._key = key
        self._source_entity = source_entity
        self._timestamp = timestamp
        self._attr_unique_id = f"{DOMAIN}_bridge_{key}"
        self._attr_name = f"TV Guide Native {name}"
        self._attr_icon = icon
        if timestamp:
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._state = None

    @property
    def available(self):
        """Only report values published by the original add-on."""
        return self._state is not None

    @property
    def native_value(self):
        """Return the validated state value."""
        if self._state is None:
            return None
        raw = self._state.state
        if raw in ("unknown", "unavailable", ""):
            return None
        return parse_timestamp(raw) if self._timestamp else parse_count(raw)

    @property
    def extra_state_attributes(self):
        """Expose reminder metadata without overwriting native sensor fields."""
        if self._state is None or self._key != "next_reminder":
            return None
        fields = ("reminder_id", "channel", "channel_id", "title", "programme_start", "minutes_before")
        return {field: self._state.attributes[field] for field in fields if field in self._state.attributes}

    @callback
    def _update_from_source(self):
        """Ignore entities that are not owned by the TV Guide add-on."""
        candidate = self.hass.states.get(self._source_entity)
        if candidate is not None and owned_state(candidate.attributes, SOURCE):
            self._state = candidate
        else:
            self._state = None
        self.async_write_ha_state()

    async def async_added_to_hass(self):
        """Subscribe to changes instead of polling."""
        await super().async_added_to_hass()
        @callback
        def on_change(event):
            self._update_from_source()
        self.async_on_remove(
            async_track_state_change_event(self.hass, [self._source_entity], on_change)
        )
        self._update_from_source()
