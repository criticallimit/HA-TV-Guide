"""Native event-driven reminders, without polling or Supervisor access."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
import re
from zoneinfo import ZoneInfo

from homeassistant.helpers.event import async_track_point_in_utc_time
from .reminder_times import next_reminder_time, retry_time

_LOGGER = logging.getLogger(__name__)


class TVGuideReminderScheduler:
    """Schedule only pending saved reminders using Home Assistant's event loop."""

    def __init__(self, hass, saved, lock: asyncio.Lock, notification_service: str = "persistent_notification.create"):
        self.hass = hass
        self.saved = saved
        self.lock = lock
        self.notification_service = notification_service
        self._cancellations = []
        self._stopped = False

    def stop(self):
        self._stopped = True
        self._cancel_timers()

    def _cancel_timers(self):
        for cancel in self._cancellations:
            cancel()
        self._cancellations.clear()

    def reschedule(self):
        """Replace timers, including after updating a reminder or a restart."""
        self._cancel_timers()
        self._stopped = False
        now = datetime.now(timezone.utc)
        for reminder in self.saved.reminders:
            when = next_reminder_time(reminder, now)
            if when is None:
                continue
            self._schedule(reminder["id"], when)

    def _schedule(self, reminder_id: str, when: datetime):
        """Schedule a single reminder (also used for bounded delivery retries)."""
        def callback(_now):
            if not self._stopped:
                self.hass.async_create_task(self._deliver(reminder_id))

        self._cancellations.append(
            async_track_point_in_utc_time(self.hass, callback, when)
        )

    async def _deliver(self, reminder_id: str):
        """Persist sent state after a successful Home Assistant notification."""
        async with self.lock:
            if self._stopped:
                return
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
                domain, service = self.notification_service.split(".", 1)
                payload = {"title": "TV Guide – Erinnerung", "message": message}
                if domain == "persistent_notification":
                    payload["notification_id"] = "tv_guide_" + re.sub(
                        r"[^a-zA-Z0-9_]+", "_", reminder_id
                    )[-180:]
                await self.hass.services.async_call(
                    domain, service, payload, blocking=True,
                )
            except Exception:
                _LOGGER.exception("TV Guide reminder notification failed")
                when = retry_time(item, datetime.now(timezone.utc))
                if when is not None and not self._stopped:
                    self._schedule(reminder_id, when)
                return
            item["sent"] = True
            item["sent_at"] = now.isoformat()
            await self.saved.async_save()
        self.reschedule()
