"""Read-only calendar of programmes obtained from the configured XMLTV feed."""

from datetime import datetime, timezone

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .channel_selection import filter_programmes
from .channel_mapping import resolved_selection, channel_labels


async def async_setup_entry(hass, entry, async_add_entities):
    """Create a programme calendar only when standalone EPG is enabled."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is not None:
        options = {**entry.data, **entry.options}
        async_add_entities([TVGuideProgrammeCalendar(coordinator, options.get("channels", []))])


class TVGuideProgrammeCalendar(CoordinatorEntity, CalendarEntity):
    """Expose a feed's programmes as Home Assistant calendar events."""

    _attr_name = "TV Guide Programmes"
    _attr_unique_id = "tv_guide_xmltv_programmes_calendar"

    def __init__(self, coordinator, selected_channels):
        super().__init__(coordinator)
        self._selected_channels = selected_channels

    def _selected_feed_channels(self):
        return resolved_selection(self._selected_channels, self.coordinator.canonical_channels)

    def _to_event(self, programme):
        try:
            start = datetime.fromisoformat(programme["start"])
            end = datetime.fromisoformat(programme["stop"])
            if start.tzinfo is None or end.tzinfo is None or end <= start:
                return None
            return CalendarEvent(
                start=start,
                end=end,
                summary=programme["title"],
                description=programme.get("description", ""),
                location=channel_labels(
                    self.coordinator.canonical_channels, self.coordinator.channels
                ).get(programme["channel"], programme["channel"]),
            )
        except (KeyError, ValueError, TypeError):
            return None

    @property
    def event(self):
        """Return the current event, or next event across all channels."""
        now = datetime.now(timezone.utc)
        events = (
            event
            for record in filter_programmes(self.coordinator.data or [], self._selected_feed_channels())
            if (event := self._to_event(record)) is not None and event.end > now
        )
        return min(events, key=lambda event: (max(event.start, now), event.start), default=None)

    async def async_get_events(self, hass, start_date, end_date):
        """Retrieve programmes overlapping the requested time window."""
        events = []
        for record in filter_programmes(self.coordinator.data or [], self._selected_channels):
            event = self._to_event(record)
            if event is not None and event.start < end_date and event.end > start_date:
                events.append(event)
        events.sort(key=lambda event: (event.start, event.location or ""))
        return events
