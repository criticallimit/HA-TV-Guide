"""Pure time calculations for native TV Guide reminders."""

from datetime import datetime, timedelta, timezone

GRACE = timedelta(minutes=5)
REMINDER_MINUTES = (5, 10, 15, 30)


def normalize_reminder_minutes(value):
    """Accept HA select values without rounding fractional or boolean input."""
    if isinstance(value, str) and value in {str(minutes) for minutes in REMINDER_MINUTES}:
        value = int(value)
    if type(value) is not int or value not in REMINDER_MINUTES:
        raise ValueError("Invalid reminder minutes")
    return value


def reminder_expiry(record):
    """Delivery stops at programme end or grace expiry; invalid dates are inert."""
    try:
        start = datetime.fromisoformat(record['start'])
        if start.tzinfo is None:
            return None
        start = start.astimezone(timezone.utc)
        duration = GRACE
        if record.get('end'):
            end = datetime.fromisoformat(record['end'])
            if end.tzinfo is None:
                return None
            end = end.astimezone(timezone.utc)
            if end <= start:
                return None
            duration = min(duration, end - start)
        return start + duration
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def next_reminder_time(record: dict, now: datetime) -> datetime | None:
    """Return UTC delivery time, or None for sent/expired records."""
    if record.get("sent"):
        return None
    try:
        start = datetime.fromisoformat(record["start"])
        minutes = normalize_reminder_minutes(record["minutes"])
        if start.tzinfo is None or now.tzinfo is None:
            return None
        now = now.astimezone(timezone.utc)
        start = start.astimezone(timezone.utc)
        expires = reminder_expiry(record)
        if expires is None or now >= expires:
            return None
        return max(now, start - timedelta(minutes=minutes))
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def retry_time(record: dict, now: datetime) -> datetime | None:
    """Retry a failed delivery after 60 seconds while the grace window remains."""
    try:
        if now.tzinfo is None:
            return None
        expires = reminder_expiry(record)
        if expires is None:
            return None
        next_try = now.astimezone(timezone.utc) + timedelta(seconds=60)
        return next_try if next_try < expires else None
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
