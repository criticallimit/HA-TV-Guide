"""Pure helpers for user-selected XMLTV channel IDs.

An empty selection means all channels; saved order is retained.
"""


def parse_channel_selection(text: str) -> list[str]:
    """Parse a comma/newline-separated list without duplicates."""
    if not isinstance(text, str) or len(text) > 16000:
        raise ValueError("Invalid channel selection")
    selection = []
    seen = set()
    for raw in text.replace("\n", ",").split(","):
        channel = raw.strip()
        if not channel:
            continue
        if len(channel) > 160 or any(ord(character) < 32 for character in channel):
            raise ValueError("Invalid channel ID")
        if channel not in seen:
            selection.append(channel)
            seen.add(channel)
        if len(selection) > 200:
            raise ValueError("Too many selected channels")
    return selection


def filter_programmes(programmes: list[dict], selected: list[str]) -> list[dict]:
    """Keep only selected channels; empty selection keeps the entire feed."""
    if not selected:
        return programmes
    allowed = set(selected)
    return [record for record in programmes if record.get("channel") in allowed]
