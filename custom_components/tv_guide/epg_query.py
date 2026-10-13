"""Query the already downloaded EPG snapshot using a native HA response action."""

from datetime import datetime
import voluptuous as vol

from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError

from .channel_mapping import resolved_selection, channel_labels
from .const import DOMAIN

SERVICE_GET_PROGRAMMES = "get_programmes"
QUERY_SCHEMA = vol.Schema({
    vol.Optional("channel_id", default=""): str,
    vol.Required("start"): str,
    vol.Required("end"): str,
    vol.Optional("limit", default=100): vol.All(vol.Coerce(int), vol.Range(min=1, max=500)),
})


def query_programmes(programmes, catalogue, feed_channels, *, channel_id, start, end, limit):
    """Return a bounded chronological subset of the cached XMLTV snapshot."""
    ids = resolved_selection([channel_id], catalogue) if channel_id else []
    if channel_id and not ids:
        return []
    allowed = set(ids)
    labels = channel_labels(catalogue, feed_channels)
    result = []
    for programme in programmes:
        if channel_id and programme.get("channel") not in allowed:
            continue
        try:
            begins = datetime.fromisoformat(programme["start"])
            finishes = datetime.fromisoformat(programme["stop"])
        except (KeyError, ValueError, TypeError):
            continue
        if begins < end and finishes > start:
            result.append({
                **programme,
                "channel_name": labels.get(programme["channel"], programme["channel"]),
            })
    result.sort(key=lambda programme: (programme["start"], programme["channel"]))
    return result[:limit]


def async_register_epg_query(hass):
    """Expose the EPG snapshot through a response-capable Home Assistant action."""
    async def handle(call):
        try:
            start = datetime.fromisoformat(call.data["start"])
            end = datetime.fromisoformat(call.data["end"])
        except ValueError as exc:
            raise HomeAssistantError("Invalid ISO 8601 timestamp") from exc
        if start.tzinfo is None or end.tzinfo is None or end <= start:
            raise HomeAssistantError("Time range must use timezone-aware start and end")
        if (end - start).total_seconds() > 7 * 86400:
            raise HomeAssistantError("Time range cannot exceed seven days")
        coordinators = hass.data.get(DOMAIN, {})
        if len(coordinators) != 1:
            raise HomeAssistantError("Exactly one TV Guide EPG feed must be configured")
        coordinator = next(iter(coordinators.values()))
        if coordinator.data is None:
            raise HomeAssistantError("No EPG snapshot available")
        records = query_programmes(
            coordinator.data, coordinator.canonical_channels,
            coordinator.channels, channel_id=call.data["channel_id"],
            start=start, end=end, limit=call.data["limit"],
        )
        return {"programmes": records, "count": len(records)}

    hass.services.async_register(
        DOMAIN, SERVICE_GET_PROGRAMMES, handle,
        schema=QUERY_SCHEMA, supports_response=SupportsResponse.ONLY,
    )


def async_remove_epg_query(hass):
    hass.services.async_remove(DOMAIN, SERVICE_GET_PROGRAMMES)
