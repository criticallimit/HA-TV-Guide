"""Map saved canonical TV Guide channel IDs to actual XMLTV feed channel IDs.

Preserve selection order, but never mistake an unavailable main channel for a
different broadcaster.
"""


def resolved_selection(selected: list[str], catalogue: list[dict]) -> list[str]:
    """Resolve canonical identifiers against the current country's XMLTV aliases."""
    if not selected:
        return []
    by_canonical = {station["id"]: station.get("xmltv_id") for station in catalogue}
    result = []
    seen = set()
    for key in selected:
        source = by_canonical.get(key, key)
        if key in by_canonical and source is None:
            continue
        if source not in seen:
            seen.add(source)
            result.append(source)
    return result


def channel_labels(catalogue: list[dict], raw_channels: list[dict]) -> dict[str, str]:
    """Map XMLTV feed IDs to human readable names, prioritizing main catalogue."""
    labels = {item["id"]: item["name"] for item in raw_channels}
    labels.update({item["xmltv_id"]: item["name"] for item in catalogue if item.get("xmltv_id")})
    return labels
