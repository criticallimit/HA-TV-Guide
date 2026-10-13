"""Pure time calculations for native TV Guide reminders."""

from datetime import datetime, timedelta, timezone

GRACE = timedelta(minutes=5)


def next_reminder_time(record: dict, now: datetime) -> datetime | None:
    """Return UTC delivery time, or None for sent/expired records."""
    if record.get("sent"):
        return None
    try:
        start = datetime.fromisoformat(record["start"])
        minutes = int(record["minutes"])
        if start.tzinfo is None or minutes not in (5, 10, 15, 30):
            return None
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    now = now.astimezone(timezone.utc)
    start = start.astimezone(timezone.utc)
    if now >= start + GRACE:
        return None
    return max(now, start - timedelta(minutes=minutes))


def retry_time(record: dict, now: datetime) -> datetime | None:
    """Retry a failed delivery after 60 seconds while the grace window remains."""
    try:
        start = datetime.fromisoformat(record["start"])
    except (KeyError, TypeError, ValueError):
        return None
    if start.tzinfo is None:
        return None
    next_try = now.astimezone(timezone.utc) + timedelta(seconds=60)
    return next_try if next_try < start.astimezone(timezone.utc) + GRACE else None
