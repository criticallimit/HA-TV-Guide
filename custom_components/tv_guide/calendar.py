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
        async_add_entities([TVGuideProgrammeCalendar(coordinator, entry)])


class TVGuideProgrammeCalendar(CoordinatorEntity, CalendarEntity):
    """Expose a feed's programmes as Home Assistant calendar events."""

    _attr_name = "TV Guide Programmes"
    _attr_unique_id = "tv_guide_xmltv_programmes_calendar"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._entry = entry

    @property
    def _selected_channels(self):
        return self._entry.options.get("channels", self._entry.data.get("channels", []))

    def _selected_programmes(self):
        records = self.coordinator.data or []
        if not self._selected_channels:
            return records
        selected = resolved_selection(self._selected_channels, self.coordinator.canonical_channels)
        return filter_programmes(records, selected) if selected else []

    def _to_event(self, programme, labels=None):
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
                location=(labels if labels is not None else channel_labels(
                    self.coordinator.canonical_channels, self.coordinator.channels
                )).get(programme["channel"], programme["channel"]),
            )
        except (KeyError, ValueError, TypeError):
            return None

    @property
    def event(self):
        """Return the current event, or next event across all channels."""
        now = datetime.now(timezone.utc)
        labels = channel_labels(self.coordinator.canonical_channels, self.coordinator.channels)
        best, best_key = None, None
        for record in self._selected_programmes():
            try:
                start, end = datetime.fromisoformat(record['start']), datetime.fromisoformat(record['stop'])
            except (KeyError, TypeError, ValueError):
                continue
            if start.tzinfo is None or end.tzinfo is None or end <= start or end <= now:
                continue
            key = (max(start, now), start)
            if best_key is None or key < best_key:
                candidate = self._to_event(record, labels)
                if candidate is not None:
                    best, best_key = candidate, key
        return best

    async def async_get_events(self, hass, start_date, end_date):
        """Retrieve programmes overlapping the requested time window."""
        events = []
        labels = channel_labels(self.coordinator.canonical_channels, self.coordinator.channels)
        for record in self._selected_programmes():
            event = self._to_event(record, labels)
            if event is not None and event.start < end_date and event.end > start_date:
                events.append(event)
        events.sort(key=lambda event: (event.start, event.location or ""))
        return events
