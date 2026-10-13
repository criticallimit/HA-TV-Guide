"""Persistent, addon-independent programme bookmarks and reminders.

Data model matches the old TV Guide API's IDs and field names for a later
explicit migration. This module does not send notifications on its own.
"""

from __future__ import annotations

from datetime import datetime, timezone

from homeassistant.helpers.storage import Store

STORAGE_VERSION = 1
MAX_ITEMS = 1000


def normalize_items(items: object, *, reminders: bool = False) -> list[dict]:
    """Validate stored records and omit expired or malformed entries."""
    if not isinstance(items, list):
        return []
    now = datetime.now(timezone.utc)
    accepted = []
    seen = set()
    for item in items[:MAX_ITEMS]:
        if not isinstance(item, dict):
            continue
        record_id = item.get("id")
        if not isinstance(record_id, str) or not record_id or len(record_id) > 200 or record_id in seen:
            continue
        try:
            start = datetime.fromisoformat(item["start"])
            end = datetime.fromisoformat(item["end"])
        except (KeyError, ValueError, TypeError):
            continue
        if start.tzinfo is None or end.tzinfo is None or start >= end or end <= now:
            continue
        if reminders:
            try:
                minutes = int(item.get("minutes", 10))
            except (ValueError, TypeError):
                continue
            if minutes not in (5, 10, 15, 30):
                continue
        else:
            minutes = None
        result = {
            "id": record_id,
            "channel": str(item.get("channel") or "")[:120],
            "channelId": str(item.get("channelId") or "")[:120],
            "title": str(item.get("title") or "")[:240],
            "start": start.isoformat(),
            "end": end.isoformat(),
        }
        if reminders:
            result.update({
                "minutes": minutes,
                "language": str(item.get("language") or "de")[:16],
                "sent": item.get("sent") is True,
            })
            if isinstance(item.get("sent_at"), str):
                result["sent_at"] = item["sent_at"][:64]
        accepted.append(result)
        seen.add(record_id)
    accepted.sort(key=lambda value: value["start"])
    return accepted


class TVGuideSavedProgrammes:
    """Manage storage for programme bookmarks and reminders in HA .storage."""

    def __init__(self, hass, entry_id: str):
        self._store = Store(hass, STORAGE_VERSION, f"tv_guide.{entry_id}.saved_programmes")
        self.bookmarks: list[dict] = []
        self.reminders: list[dict] = []
        self._subscribers = set()

    def subscribe(self, callback):
        """Subscribe an entity to changes in native saved lists."""
        self._subscribers.add(callback)

    def unsubscribe(self, callback):
        self._subscribers.discard(callback)

    async def async_load(self):
        """Load records without accessing old add-on files."""
        data = await self._store.async_load() or {}
        if not isinstance(data, dict):
            data = {}
        self.bookmarks = normalize_items(data.get("bookmarks"))
        self.reminders = normalize_items(data.get("reminders"), reminders=True)

    async def async_save(self):
        """Persist both collections atomically using HA's Store abstraction."""
        self.bookmarks = normalize_items(self.bookmarks)
        self.reminders = normalize_items(self.reminders, reminders=True)
        await self._store.async_save({
            "bookmarks": self.bookmarks,
            "reminders": self.reminders,
        })
        for callback in tuple(self._subscribers):
            callback()
