"""Calculate the next unsent TV Guide reminder for a Home Assistant timestamp sensor."""

from datetime import datetime, timedelta, timezone

from .reminder_times import next_reminder_time


def pending_reminders(reminders: list[dict], now: datetime | None = None):
    """Keep only unsent reminders still eligible for delivery."""
    current = now or datetime.now(timezone.utc)
    return [record for record in reminders if next_reminder_time(record,current) is not None
            and (not record.get('end') or datetime.fromisoformat(record['end']) > current)]


def next_pending_reminder(reminders: list[dict], now: datetime | None = None):
    """Return (delivery time, record) or (None, None), without mutating storage."""
    current = now or datetime.now(timezone.utc)
    candidates = []
    for record in pending_reminders(reminders,current):
        due = datetime.fromisoformat(record['start']).astimezone(timezone.utc) - timedelta(minutes=int(record['minutes']))
        candidates.append((due, record))
    if not candidates:
        return None, None
    return min(candidates, key=lambda item: (item[0], item[1]["id"]))
