"""Read-only calendar of programmes obtained from the configured XMLTV feed."""

from datetime import datetime, timezone

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    """Create a programme calendar only when standalone EPG is enabled."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is not None:
        async_add_entities([TVGuideProgrammeCalendar(coordinator)])


class TVGuideProgrammeCalendar(CoordinatorEntity, CalendarEntity):
    """Expose a feed's programmes as Home Assistant calendar events."""

    _attr_name = "TV Guide Programmes"
    _attr_unique_id = "tv_guide_xmltv_programmes_calendar"

    def __init__(self, coordinator):
        super().__init__(coordinator)

    @staticmethod
    def _to_event(programme):
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
                location=programme["channel"],
            )
        except (KeyError, ValueError, TypeError):
            return None

    @property
    def event(self):
        """Return the current event, or next event across all channels."""
        now = datetime.now(timezone.utc)
        events = (
            event
            for record in (self.coordinator.data or [])
            if (event := self._to_event(record)) is not None and event.end > now
        )
        return min(events, key=lambda event: (max(event.start, now), event.start), default=None)

    async def async_get_events(self, hass, start_date, end_date):
        """Retrieve programmes overlapping the requested time window."""
        events = []
        for record in self.coordinator.data or []:
            event = self._to_event(record)
            if event is not None and event.start < end_date and event.end > start_date:
                events.append(event)
        events.sort(key=lambda event: (event.start, event.location or ""))
        return events
