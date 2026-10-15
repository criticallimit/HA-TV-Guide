"""Bundled country channel catalogues copied from the TV-Guide add-on.

No network calls are made to obtain the standard sender list.
"""

from __future__ import annotations

import json
from pathlib import Path

CATALOG_FILES = {
    "de": "channels.json",
    "at": "channels_at.json",
    "ch": "channels_ch.json",
    "nl": "channels_nl.json",
    "be": "channels_be.json",
    "dk": "channels_dk.json",
    "no": "channels_no.json",
    "fr": "channels_fr.json",
    "se": "channels_se.json",
    "gb": "channels_gb.json",
}

CATALOG_DIR = Path(__file__).with_name("catalogs")


def load_channel_catalog(country: str) -> list[dict]:
    """Return country's canonical ordered sender list."""
    filename = CATALOG_FILES.get(country)
    if filename is None:
        return []
    with (CATALOG_DIR / filename).open(encoding="utf-8") as stream:
        catalog = json.load(stream)
    return sorted(catalog["channels"], key=lambda channel: channel["order"])


def resolve_catalogue_channels(country: str, xmltv_channels: list[dict]) -> list[dict]:
    """Keep canonical country order and map to actual feed IDs when available.

    Unmatched main channels remain in the result, marked unavailable, instead
    of disappearing from the main-station list.
    """
    feed_by_id = {item["id"]: item for item in xmltv_channels}
    folded = {}
    for item in feed_by_id.values():
        key = item["id"].casefold()
        # Distinct XMLTV IDs are case sensitive. Only use a folded alias if unique.
        folded[key] = None if key in folded else item
    result = []
    for channel in load_channel_catalog(country):
        candidates = [*channel.get("xmltv_ids", []), channel["id"], channel["name"], *channel.get("aliases", [])]
        match = None
        for value in candidates:
            match = feed_by_id.get(value) or folded.get(value.casefold())
            if match is not None:
                break
        result.append({
            "id": channel["id"],
            "name": channel["name"],
            "order": channel["order"],
            "xmltv_id": match["id"] if match else None,
            "available": match is not None,
        })
    return result
