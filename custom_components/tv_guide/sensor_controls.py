"""User-facing controls for this integration's own native entities."""
from .const import DOMAIN

NATIVE_SENSORS = {
    "sensor_next_reminder": ("sensor", "tv_guide_native_next_reminder"),
    "sensor_bookmark_count": ("sensor", "tv_guide_native_saved_bookmarks_count"),
    "sensor_reminder_count": ("sensor", "tv_guide_native_saved_reminders_count"),
    "sensor_last_update": ("sensor", "tv_guide_native_epg_last_successful_refresh"),
    "sensor_refresh_running": ("binary_sensor", "tv_guide_native_refresh_running"),
}


def _owned_entities(hass, entry_id):
    from homeassistant.helpers import entity_registry as er
    registry = er.async_get(hass)
    result = {}
    for key, (domain, unique_id) in NATIVE_SENSORS.items():
        entity_id = registry.async_get_entity_id(domain, DOMAIN, unique_id)
        entity = registry.async_get(entity_id) if entity_id else None
        if entity is not None and entity.config_entry_id == entry_id:
            result[key] = entity
    return registry, result


def sensor_settings(hass, entry_id):
    _, entities = _owned_entities(hass, entry_id)
    return {key:key in entities and entities[key].disabled_by is None for key in NATIVE_SENSORS}


def set_sensor_settings(hass, entry_id, settings):
    """Apply explicit UI toggles without touching add-on or other-entry entities."""
    from homeassistant.helpers import entity_registry as er
    changes = {key:value for key,value in settings.items() if key in NATIVE_SENSORS}
    if any(type(value) is not bool for value in changes.values()):
        raise ValueError("Invalid sensor setting")
    registry, entities = _owned_entities(hass, entry_id)
    for key, enabled in changes.items():
        entity = entities.get(key)
        if entity is None:
            continue
        disabled_by = None if enabled else er.RegistryEntryDisabler.USER
        if entity.disabled_by != disabled_by:
            registry.async_update_entity(entity.entity_id, disabled_by=disabled_by)
