"""Pure validation helpers for states published by the existing TV Guide add-on."""

from datetime import datetime


def parse_count(value: object) -> int | None:
    """Validate a nonnegative integral count without inventing zero on failure."""
    try:
        text = str(value)
        if not text.isascii() or not text.isdecimal():
            return None
        number = int(text)
        return number if number >= 0 else None
    except (TypeError, ValueError):
        return None


def parse_timestamp(value: object) -> datetime | None:
    """Accept only timezone-aware ISO 8601 timestamps."""
    if not isinstance(value, str) or not value:
        return None
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return timestamp if timestamp.tzinfo is not None and timestamp.utcoffset() is not None else None


def owned_state(attributes: object, source: str) -> bool:
    """Verify the explicit source marker rather than relying on entity IDs."""
    return isinstance(attributes, dict) and attributes.get("tv_guide_source") == source
