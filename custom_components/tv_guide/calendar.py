"""Read-only calendar of programmes from the integration’s own EPG snapshot."""

from datetime import datetime, timezone

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .channel_selection import filter_programmes
from .channel_mapping import resolved_selection, channel_labels


async def async_setup_entry(hass, entry, async_add_entities):
    """Create a programme calendar when the native EPG coordinator is loaded."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is not None:
        async_add_entities([TVGuideProgrammeCalendar(coordinator, entry)])


class TVGuideProgrammeCalendar(CoordinatorEntity, CalendarEntity):
    """Expose the guide's programmes as Home Assistant calendar events."""

    _attr_has_entity_name = True
    _attr_translation_key = "programmes"
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

    def _events_for_range(self, records, catalogue, channels, selection, start_date, end_date):
        """Filter and build events from one captured snapshot in a worker."""
        events = []
        if selection:
            selected = resolved_selection(selection, catalogue)
            if not selected:
                return events
            records = filter_programmes(records, selected)
        labels = channel_labels(catalogue, channels)
        for record in records:
            event = self._to_event(record, labels)
            if event is not None and event.start < end_date and event.end > start_date:
                events.append(event)
        events.sort(key=lambda event: (event.start, event.location or ""))
        return events

    async def async_get_events(self, hass, start_date, end_date):
        """Retrieve overlapping programmes without blocking HA's event loop."""
        return await hass.async_add_executor_job(
            self._events_for_range, self.coordinator.data or [],
            self.coordinator.canonical_channels, self.coordinator.channels,
            list(self._selected_channels), start_date, end_date,
        )
