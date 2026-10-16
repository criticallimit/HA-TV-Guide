"""Home Assistant actions for persistent bookmarks and reminders."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import voluptuous as vol
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .languages import LANGUAGES
from .saved_programmes import MAX_ITEMS, MAX_CHANNEL_ID_LENGTH, normalize_items, normalize_reminder_minutes

SERVICE_BOOKMARK = "save_bookmark"
SERVICE_REMINDER = "save_reminder"
SERVICE_REMOVE = "remove_saved_programme"
SERVICE_GET_SAVED = "get_saved_programmes"

BASE = {
    vol.Required("id"): vol.All(str, vol.Length(min=1, max=200)),
    vol.Required("title"): vol.All(str, vol.Length(min=1, max=240)),
    vol.Required("channel"): vol.All(str, vol.Length(min=1, max=120)),
    vol.Required("channel_id"): vol.All(str, vol.Length(min=1, max=MAX_CHANNEL_ID_LENGTH)),
    vol.Required("start"): str,
    vol.Required("end"): str,
}
BOOKMARK_SCHEMA = vol.Schema(BASE)
REMINDER_SCHEMA = vol.Schema({**BASE, vol.Optional("minutes", default=10): normalize_reminder_minutes,
    vol.Optional("language"):vol.In(['auto',*LANGUAGES])})
REMOVE_SCHEMA = vol.Schema({
    vol.Required("id"): vol.All(str, vol.Length(min=1, max=200)),
    vol.Required("kind"): vol.In(["bookmark", "reminder", "programme"]),
})


async def async_register_saved_services(hass):
    """Register one set of actions shared by the single TV Guide instance."""
    lock = hass.data.setdefault(DOMAIN + "_saved_lock", asyncio.Lock())

    async def handle_get_saved(_call):
        stores = hass.data.get(DOMAIN + "_saved", {})
        if len(stores) != 1:
            raise HomeAssistantError("Exactly one TV Guide entry must be loaded")
        entry_id, saved = next(iter(stores.items()))
        async with lock:
            if hass.data.get(DOMAIN + "_saved", {}).get(entry_id) is not saved:
                raise HomeAssistantError("TV Guide is unloading")
            # A read does not write storage, send notifications or expose expired items.
            return {
                "bookmarks": normalize_items(saved.bookmarks),
                "reminders": normalize_items(saved.reminders, reminders=True),
            }

    hass.services.async_register(
        DOMAIN, SERVICE_GET_SAVED, handle_get_saved,
        schema=vol.Schema({}), supports_response=SupportsResponse.ONLY,
    )

    async def handle(call):
        stores = hass.data.get(DOMAIN + "_saved", {})
        if len(stores) != 1:
            raise HomeAssistantError("Exactly one TV Guide entry must be loaded")
        entry_id, saved = next(iter(stores.items()))
        action = call.service
        async with lock:
            if hass.data.get(DOMAIN + "_saved", {}).get(entry_id) is not saved:
                raise HomeAssistantError("TV Guide is unloading")
            previous_bookmarks = [dict(item) for item in saved.bookmarks]
            previous_reminders = [dict(item) for item in saved.reminders]
            if action == SERVICE_REMOVE:
                keys = ("bookmarks","reminders") if call.data["kind"] == "programme" else ("bookmarks",) if call.data["kind"] == "bookmark" else ("reminders",)
                for key in keys:
                    setattr(saved, key, [item for item in getattr(saved, key) if item["id"] != call.data["id"]])
            else:
                key = "bookmarks" if action == SERVICE_BOOKMARK else "reminders"
                item = {
                    "id": call.data["id"],
                    "title": call.data["title"],
                    "channel": call.data["channel"],
                    "channelId": call.data["channel_id"],
                    "start": call.data["start"],
                    "end": call.data["end"],
                }
                if action == SERVICE_REMINDER:
                    item.update({"minutes": call.data["minutes"], "sent": False, "language": call.data.get('language') or hass.config.language})
                try:
                    start = datetime.fromisoformat(item["start"])
                    end = datetime.fromisoformat(item["end"])
                except ValueError as exc:
                    raise HomeAssistantError("Invalid programme dates") from exc
                if start.tzinfo is None or end.tzinfo is None or end <= start or end <= datetime.now(timezone.utc):
                    raise HomeAssistantError("Programme must have a valid future end time")
                if action == SERVICE_REMINDER and start <= datetime.now(timezone.utc):
                    raise HomeAssistantError("Reminders can only be created before programme start")
                normalized = normalize_items([item], reminders=action == SERVICE_REMINDER)
                if not normalized:
                    raise HomeAssistantError("Invalid programme")
                existing = normalize_items(getattr(saved, key), reminders=action == SERVICE_REMINDER)
                remaining = [old for old in existing if old["id"] != item["id"]]
                if len(remaining) >= MAX_ITEMS:
                    raise HomeAssistantError(f"The saved list is limited to {MAX_ITEMS} programmes")
                setattr(saved, key, remaining + normalized)
            cancelled = False
            try:
                persistence = asyncio.create_task(saved.async_save())
                # Store writes can outlive their cancelled caller. Keep the
                # lock until the commit finishes, including on unload.
                while not persistence.done():
                    try:
                        await asyncio.shield(persistence)
                    except asyncio.CancelledError:
                        cancelled = True
                persistence.result()
            except (Exception, asyncio.CancelledError):
                saved.bookmarks = previous_bookmarks
                saved.reminders = previous_reminders
                raise
            scheduler = hass.data.get(DOMAIN + "_reminder_schedulers", {}).get(entry_id)
            if scheduler is not None:
                scheduler.reschedule()
            if cancelled:
                raise asyncio.CancelledError

    hass.services.async_register(DOMAIN, SERVICE_BOOKMARK, handle, schema=BOOKMARK_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_REMINDER, handle, schema=REMINDER_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_REMOVE, handle, schema=REMOVE_SCHEMA)


def async_remove_saved_services(hass):
    """Unregister all TV Guide actions when the last entry unloads."""
    for service in (SERVICE_BOOKMARK, SERVICE_REMINDER, SERVICE_REMOVE, SERVICE_GET_SAVED):
        hass.services.async_remove(DOMAIN, service)
