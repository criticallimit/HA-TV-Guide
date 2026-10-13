"""Native event-driven reminders, without polling or Supervisor access."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
import re
from zoneinfo import ZoneInfo

from homeassistant.helpers.event import async_track_point_in_utc_time

_LOGGER = logging.getLogger(__name__)


class TVGuideReminderScheduler:
    """Schedule only pending saved reminders using Home Assistant's event loop."""

    def __init__(self, hass, saved, lock: asyncio.Lock):
        self.hass = hass
        self.saved = saved
        self.lock = lock
        self._cancellations = []

    def stop(self):
        for cancel in self._cancellations:
            cancel()
        self._cancellations.clear()

    def reschedule(self):
        """Replace timers, including after updating a reminder or a restart."""
        self.stop()
        now = datetime.now(timezone.utc)
        for reminder in self.saved.reminders:
            if reminder.get("sent"):
                continue
            try:
                start = datetime.fromisoformat(reminder["start"])
                if start.tzinfo is None:
                    continue
                when = start - timedelta(minutes=int(reminder["minutes"]))
                if now >= start + timedelta(minutes=5):
                    continue
                when = max(when.astimezone(timezone.utc), now)
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
            reminder_id = reminder["id"]

            def callback(_now, item_id=reminder_id):
                self.hass.async_create_task(self._deliver(item_id))

            self._cancellations.append(
                async_track_point_in_utc_time(self.hass, callback, when)
            )

    async def _deliver(self, reminder_id: str):
        """Persist sent state after a successful Home Assistant notification."""
        async with self.lock:
            item = next((r for r in self.saved.reminders if r["id"] == reminder_id), None)
            if item is None or item.get("sent"):
                return
            start = datetime.fromisoformat(item["start"])
            now = datetime.now(timezone.utc)
            if now >= start + timedelta(minutes=5):
                return
            time_text = start.astimezone(ZoneInfo(self.hass.config.time_zone)).strftime("%H:%M")
            message = f'{item["channel"]}: „{item["title"]}“ beginnt um {time_text} Uhr.'
            try:
                await self.hass.services.async_call(
                    "persistent_notification", "create",
                    {
                        "title": "TV Guide – Erinnerung",
                        "message": message,
                        "notification_id": "tv_guide_" + re.sub(
                            r"[^a-zA-Z0-9_]+", "_", reminder_id
                        )[-180:],
                    },
                    blocking=True,
                )
            except Exception:
                _LOGGER.exception("TV Guide reminder notification failed")
                return
            item["sent"] = True
            item["sent_at"] = now.isoformat()
            await self.saved.async_save()
        self.reschedule()
