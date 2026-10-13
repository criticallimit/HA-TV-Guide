"""Read channel names from XMLTV metadata without requesting another feed."""

from __future__ import annotations

from io import BytesIO
from xml.etree import ElementTree as ET

from .xmltv import MAX_XML_SIZE

MAX_CHANNELS = 10000


def parse_channel_catalog(payload: bytes) -> list[dict[str, str]]:
    """Parse bounded channel metadata, preserving feed order and IDs."""
    if len(payload) > MAX_XML_SIZE:
        raise ValueError("XMLTV feed exceeds maximum size")
    if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise ValueError("DTD and entity declarations are not allowed")
    channels: list[dict[str, str]] = []
    seen: set[str] = set()
    for _, element in ET.iterparse(BytesIO(payload), events=("end",)):
        if element.tag != "channel":
            continue
        channel_id = element.get("id", "").strip()
        if channel_id and channel_id not in seen:
            names = [
                " ".join(node.itertext()).strip()
                for node in element.findall("display-name")
            ]
            name = next((value for value in names if value), channel_id)
            channels.append({"id": channel_id[:160], "name": name[:200]})
            seen.add(channel_id)
        element.clear()
        if len(channels) >= MAX_CHANNELS:
            break
    return channels
