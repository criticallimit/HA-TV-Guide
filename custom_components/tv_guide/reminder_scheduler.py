"""Event-driven TV Guide reminders without polling."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
from hashlib import sha256
from zoneinfo import ZoneInfo

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_point_in_utc_time
from .reminder_times import next_reminder_time, retry_time, reminder_expiry
from .notification_text import reminder_text

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
        self._generation = 0
        self._tasks = set()
        self._pending_sent = set()
        self._stop_task = None
        self._cancel_shutdown = hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP, self._async_stop_on_shutdown
        )

    async def _async_stop_on_shutdown(self, _event):
        # The one-shot bus listener has already removed itself.
        self._cancel_shutdown = None
        await self.async_stop()

    def stop(self):
        self._stopped = True
        if self._cancel_shutdown is not None:
            self._cancel_shutdown()
            self._cancel_shutdown = None
        self._cancel_timers()

    async def async_stop(self):
        """Stop new work and finish any delivery already using the saved store."""
        self.stop()
        if self._stop_task is None:
            self._stop_task = asyncio.create_task(self._async_drain())
        await asyncio.shield(self._stop_task)

    async def _async_drain(self):
        if self._tasks:
            await asyncio.gather(*tuple(self._tasks), return_exceptions=True)

    def _cancel_timers(self):
        self._generation += 1
        for cancel in self._cancellations:
            cancel()
        self._cancellations.clear()

    def reschedule(self):
        """Replace timers, including after updating a reminder or a restart."""
        if self._stopped:
            return
        self._cancel_timers()
        now = datetime.now(timezone.utc)
        for reminder in self.saved.reminders:
            if reminder["id"] in self._pending_sent and reminder.get("sent"):
                self._schedule(reminder["id"], now + timedelta(seconds=60))
                continue
            when = next_reminder_time(reminder, now)
            if when is None:
                continue
            self._schedule(reminder["id"], when)
        checkpoints = []
        for item in [*getattr(self.saved,"bookmarks",[]), *self.saved.reminders]:
            if item.get("end"):
                checkpoints.append(max(now,datetime.fromisoformat(item["end"])))
        for item in self.saved.reminders:
            if not item.get("sent"):
                expires = reminder_expiry(item)
                if expires is not None and expires > now:
                    checkpoints.append(expires)
        if checkpoints:
            self._schedule_cleanup(min(checkpoints))

    def _schedule_cleanup(self, when):
        generation = self._generation
        @callback
        def on_expiry(_now):
            if not self._stopped and generation == self._generation:
                task = self.hass.async_create_task(self._cleanup())
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)
        self._cancellations.append(async_track_point_in_utc_time(self.hass,on_expiry,when))

    async def _cleanup(self):
        """Expire saved records and notify timestamp/count entities at time boundaries."""
        async with self.lock:
            if self._stopped:
                return
            bookmarks = [dict(item) for item in getattr(self.saved,"bookmarks",[])]
            reminders = [dict(item) for item in self.saved.reminders]
            try:
                await self.saved.async_save()
            except Exception:
                self.saved.bookmarks = bookmarks
                self.saved.reminders = reminders
                _LOGGER.exception("TV Guide could not persist expired saved items")
                if not self._stopped:
                    self._schedule_cleanup(datetime.now(timezone.utc)+timedelta(seconds=60))
                return
            self._pending_sent.intersection_update(item["id"] for item in self.saved.reminders)
        self.reschedule()

    def _schedule(self, reminder_id: str, when: datetime):
        """Schedule a single reminder (also used for bounded delivery retries)."""
        generation = self._generation

        @callback
        def on_due(_now):
            if not self._stopped and generation == self._generation:
                task = self.hass.async_create_task(self._deliver(reminder_id))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)

        self._cancellations.append(
            async_track_point_in_utc_time(self.hass, on_due, when)
        )

    async def _deliver(self, reminder_id: str):
        """Persist sent state after a successful Home Assistant notification."""
        async with self.lock:
            if self._stopped:
                return
            item = next((r for r in self.saved.reminders if r["id"] == reminder_id), None)
            if reminder_id in self._pending_sent:
                if item is None or item.get("sent"):
                    await self._persist_sent(reminder_id)
                    return
                # A user replaced the reminder; this is a new delivery request.
                self._pending_sent.discard(reminder_id)
            if item is None or item.get("sent"):
                return
            start = datetime.fromisoformat(item["start"])
            now = datetime.now(timezone.utc)
            due = next_reminder_time(item, now)
            if due is None or due > now:
                return
            try:
                time_text = start.astimezone(ZoneInfo(self.hass.config.time_zone)).strftime("%H:%M")
                domain, service = self.notification_service.split(".", 1)
                payload = await self.hass.async_add_executor_job(reminder_text, dict(item), time_text, getattr(self.hass.config,'language','de'))
                if domain == "persistent_notification":
                    payload["notification_id"] = "tv_guide_" + sha256(reminder_id.encode("utf-8")).hexdigest()
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
            self._pending_sent.add(reminder_id)
            await self._persist_sent(reminder_id)

    async def _persist_sent(self, reminder_id):
        """Retry only storage after delivery succeeded, never resend the notification."""
        try:
            await self.saved.async_save()
        except Exception:
            _LOGGER.exception("TV Guide could not persist delivered reminder")
            if not self._stopped:
                self._schedule(reminder_id, datetime.now(timezone.utc) + timedelta(seconds=60))
            return
        self._pending_sent.discard(reminder_id)
        self.reschedule()
