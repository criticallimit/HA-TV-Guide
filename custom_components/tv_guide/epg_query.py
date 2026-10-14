"""Query the already downloaded EPG snapshot using a native HA response action."""

from datetime import datetime, timezone
from functools import partial
from hashlib import sha256
import voluptuous as vol

from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError

from .channel_mapping import resolved_selection, channel_labels
from .const import DOMAIN
from .channel_selection import parse_channel_selection

SERVICE_GET_PROGRAMMES = "get_programmes"
SERVICE_GET_CHANNELS = "get_channels"
SERVICE_SET_CHANNELS = "set_channels"
SET_CHANNELS_SCHEMA = vol.Schema({vol.Required("channels"): [str]})
QUERY_SCHEMA = vol.Schema({
    vol.Optional("channel_id", default=""): str,
    vol.Required("start"): str,
    vol.Required("end"): str,
    vol.Optional("limit", default=100): vol.All(vol.Coerce(int), vol.Range(min=1, max=500)),
})


def programme_id(channel_id: str, start: datetime) -> str:
    """Stable native ID regardless of sender alias or timestamp offset."""
    key = f"{channel_id}\n{start.astimezone(timezone.utc).isoformat()}"
    return "native_" + sha256(key.encode("utf-8")).hexdigest()


def query_programmes(programmes, catalogue, feed_channels, *, channel_id, start, end, limit, selected=None):
    """Return a bounded chronological subset of the cached XMLTV snapshot."""
    chosen = set(resolved_selection(selected or [], catalogue))
    if selected and not chosen:
        return []
    ids = set(resolved_selection([channel_id], catalogue)) if channel_id else chosen
    if selected and channel_id:
        ids &= chosen
    if (channel_id or selected) and not ids:
        return []
    allowed = ids
    labels = channel_labels(catalogue, feed_channels)
    result = []
    for programme in programmes:
        if (channel_id or selected) and programme.get("channel") not in allowed:
            continue
        try:
            begins = datetime.fromisoformat(programme["start"])
            finishes = datetime.fromisoformat(programme["stop"])
        except (KeyError, ValueError, TypeError):
            continue
        if begins.tzinfo is None or finishes.tzinfo is None or finishes <= begins:
            continue
        if begins < end and finishes > start:
            result.append({
                **programme,
                "id": programme_id(programme["channel"], begins),
                "channel_name": labels.get(programme["channel"], programme["channel"]),
            })
    result.sort(key=lambda programme: (datetime.fromisoformat(programme["start"]).timestamp(), programme["channel"]))
    return result[:limit]


def channel_payload(coordinator, selected: list[str]) -> dict:
    """Expose main catalog and additional feed channels for future UI clients."""
    main = coordinator.canonical_channels
    listed = {item["xmltv_id"] for item in main if item.get("xmltv_id")}
    extras = [
        {"id": item["id"], "name": item["name"], "xmltv_id": item["id"], "available": True}
        for item in coordinator.channels if item["id"] not in listed
    ]
    ordered = [dict(item) for item in main] + extras
    priority = {value: index for index, value in enumerate(selected)}
    for channel in ordered:
        key = channel["id"] if channel["id"] in priority else channel.get("xmltv_id")
        channel["selected"] = not selected or key in priority
        channel["_sort"] = priority.get(key, len(priority))
    if selected:
        ordered.sort(key=lambda item: (item["_sort"], 0 if item["selected"] else 1))
    for channel in ordered:
        channel.pop("_sort")
    return {"channels": ordered, "count": len(ordered), "country": coordinator.country}


def async_register_epg_query(hass):
    """Expose the EPG snapshot through a response-capable Home Assistant action."""
    async def handle(call):
        try:
            start = datetime.fromisoformat(call.data["start"])
            end = datetime.fromisoformat(call.data["end"])
        except (ValueError, TypeError) as exc:
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
        entry_id = next(iter(coordinators))
        entry = hass.config_entries.async_get_entry(entry_id)
        options = {**entry.data, **entry.options} if entry else {}
        records = await hass.async_add_executor_job(partial(query_programmes,
            coordinator.data, coordinator.canonical_channels,
            coordinator.channels, channel_id=call.data["channel_id"],
            start=start, end=end, limit=call.data["limit"] + 1,
            selected=options.get("channels", []),
        ))
        limit = call.data["limit"]
        return {"programmes": records[:limit], "count": min(len(records), limit), "truncated": len(records) > limit}

    async def handle_channels(_call):
        coordinators = hass.data.get(DOMAIN, {})
        if len(coordinators) != 1:
            raise HomeAssistantError("Exactly one TV Guide EPG feed must be configured")
        entry_id, coordinator = next(iter(coordinators.items()))
        config_entry = hass.config_entries.async_get_entry(entry_id)
        options = {**config_entry.data, **config_entry.options} if config_entry else {}
        return channel_payload(coordinator, options.get("channels", []))

    async def handle_set_channels(call):
        coordinators = hass.data.get(DOMAIN, {})
        if len(coordinators) != 1:
            raise HomeAssistantError("Exactly one TV Guide EPG feed must be configured")
        entry_id, coordinator = next(iter(coordinators.items()))
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None:
            raise HomeAssistantError("TV Guide config entry not found")
        raw = call.data["channels"]
        if not all(isinstance(value, str) and "," not in value for value in raw):
            raise HomeAssistantError("Invalid channel IDs")
        try:
            selected = parse_channel_selection(",".join(raw))
        except ValueError as exc:
            raise HomeAssistantError("Invalid channel selection") from exc
        known = {station["id"] for station in coordinator.canonical_channels}
        known.update(station["id"] for station in coordinator.channels)
        known.update(
            station["xmltv_id"] for station in coordinator.canonical_channels
            if station.get("xmltv_id")
        )
        if any(channel not in known for channel in selected):
            raise HomeAssistantError("Unknown channel in selection")
        hass.config_entries.async_update_entry(
            entry, options={**entry.options, "channels": selected}
        )

    hass.services.async_register(
        DOMAIN, SERVICE_SET_CHANNELS, handle_set_channels,
        schema=SET_CHANNELS_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN, SERVICE_GET_CHANNELS, handle_channels,
        supports_response=SupportsResponse.ONLY,
    )

    hass.services.async_register(
        DOMAIN, SERVICE_GET_PROGRAMMES, handle,
        schema=QUERY_SCHEMA, supports_response=SupportsResponse.ONLY,
    )


def async_remove_epg_query(hass):
    hass.services.async_remove(DOMAIN, SERVICE_GET_PROGRAMMES)
    hass.services.async_remove(DOMAIN, SERVICE_GET_CHANNELS)
    hass.services.async_remove(DOMAIN, SERVICE_SET_CHANNELS)
