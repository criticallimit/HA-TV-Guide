"""Sensors backed exclusively by this integration's own data."""

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from datetime import datetime, timezone
from .next_reminder import next_pending_reminder, pending_reminders
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.core import callback

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    """Create entities from the native coordinator and saved records."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    entities = []
    if coordinator is not None:
        entities.extend([TVGuideProgrammeCount(coordinator), TVGuideChannelsCount(coordinator), TVGuideLastRefresh(coordinator)])
    saved = hass.data.get(DOMAIN + "_saved", {}).get(entry.entry_id)
    if saved is not None:
        entities.extend([TVGuideSavedCount(saved, "bookmarks"), TVGuideSavedCount(saved, "reminders"), TVGuideNextReminder(saved)])
    async_add_entities(entities)


class TVGuideProgrammeCount(CoordinatorEntity, SensorEntity):
    """Show the number of downloaded, parsed programmes."""

    _attr_name = "TV Guide EPG programmes"
    _attr_unique_id = "tv_guide_native_epg_programme_count"
    _attr_icon = "mdi:television-guide"
    _attr_native_unit_of_measurement = "programmes"

    def __init__(self, coordinator):
        super().__init__(coordinator)

    @property
    def available(self):
        """Remain unavailable when the coordinator cannot supply EPG data."""
        return self.coordinator.last_update_success and self.coordinator.data is not None

    @property
    def native_value(self):
        """Return count only when valid EPG data is available."""
        if self.coordinator.data is None:
            return None
        return len(self.coordinator.data)


class TVGuideChannelsCount(CoordinatorEntity, SensorEntity):
    """Expose catalogue coverage, including stations with missing feed data."""

    _attr_name = "TV Guide EPG channels"
    _attr_unique_id = "tv_guide_native_epg_channels_count"
    _attr_icon = "mdi:television-classic"
    _attr_native_unit_of_measurement = "channels"

    def __init__(self, coordinator):
        super().__init__(coordinator)

    @property
    def available(self):
        return self.coordinator.last_update_success and self.coordinator.data is not None

    @property
    def native_value(self):
        if self.coordinator.data is None:
            return None
        if self.coordinator.canonical_channels:
            return sum(1 for station in self.coordinator.canonical_channels if station["available"])
        return len(self.coordinator.channels)

    @property
    def extra_state_attributes(self):
        catalogue = self.coordinator.canonical_channels
        if catalogue:
            return {
                "country": self.coordinator.country,
                "main_channels_total": len(catalogue),
                "unmatched_main_channels": [
                    channel["id"] for channel in catalogue if not channel["available"]
                ][:100],
            }
        return {"country": self.coordinator.country}


class TVGuideSavedCount(SensorEntity):
    """Count saved native items from the native saved store."""

    _attr_should_poll = False

    def __init__(self, saved, kind):
        self._saved = saved
        self._kind = kind
        self._attr_name = f"TV Guide saved {kind}"
        self._attr_unique_id = f"tv_guide_native_saved_{kind}_count"
        self._attr_icon = "mdi:bookmark" if kind == "bookmarks" else "mdi:alarm"

    @property
    def native_value(self):
        if self._kind == 'reminders':
            return len(pending_reminders(self._saved.reminders))
        return len(self._saved.bookmarks)

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self._saved.subscribe(self._notify)
        self.async_on_remove(lambda: self._saved.unsubscribe(self._notify))

    @callback
    def _notify(self):
        self.async_write_ha_state()


class TVGuideNextReminder(SensorEntity):
    """Next pending reminder based exclusively on native saved entries."""

    _attr_should_poll = False
    _attr_name = "TV Guide next native reminder"
    _attr_unique_id = "tv_guide_native_next_reminder"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:alarm"

    def __init__(self, saved):
        self._saved = saved

    @property
    def native_value(self):
        when, _ = next_pending_reminder(self._saved.reminders)
        return when

    @property
    def extra_state_attributes(self):
        _, item = next_pending_reminder(self._saved.reminders)
        if item is None:
            return None
        return {
            "reminder_id": item["id"],
            "channel": item["channel"],
            "channel_id": item["channelId"],
            "title": item["title"],
            "programme_start": item["start"],
            "minutes_before": item["minutes"],
        }

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self._saved.subscribe(self._notify)
        self.async_on_remove(lambda: self._saved.unsubscribe(self._notify))

    @callback
    def _notify(self):
        self.async_write_ha_state()


class TVGuideLastRefresh(CoordinatorEntity, SensorEntity):
    """Last successful native EPG refresh; from the native coordinator."""

    _attr_name = "TV Guide last native EPG update"
    _attr_unique_id = "tv_guide_native_epg_last_successful_refresh"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:update"

    def __init__(self, coordinator):
        super().__init__(coordinator)

    @property
    def native_value(self):
        return self.coordinator.last_successful_refresh

    @property
    def extra_state_attributes(self):
        """Report the successful snapshot source and latest bounded attempts."""
        return {
            "active_source": self.coordinator.active_source,
            "source_attempts": [dict(item) for item in self.coordinator.source_attempts],
        }
