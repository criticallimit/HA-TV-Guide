"""Calculate the next unsent TV Guide reminder for a native timestamp sensor."""

from datetime import datetime, timezone

from .reminder_times import next_reminder_time


def next_pending_reminder(reminders: list[dict], now: datetime | None = None):
    """Return (delivery time, record) or (None, None), without mutating storage."""
    current = now or datetime.now(timezone.utc)
    candidates = []
    for record in reminders:
        time = next_reminder_time(record, current)
        if time is not None:
            candidates.append((time, record))
    if not candidates:
        return None, None
    return min(candidates, key=lambda item: (item[0], item[1]["id"]))
