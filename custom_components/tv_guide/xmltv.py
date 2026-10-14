"""Standalone, network-free XMLTV programme parsing.

This module does not fetch URLs and is independent of the add-on.
"""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import re
from xml.etree import ElementTree as ET

MAX_XML_SIZE = 8 * 1024 * 1024
MAX_PROGRAMMES = 50000
_XMLTV_TIME = re.compile(r"^(\d{14})(?:\s*([+-]\d{4}))?$")


def parse_xmltv_time(value: str | None) -> datetime | None:
    """Parse XMLTV times; reject missing timezone to avoid ambiguous scheduling."""
    if not value:
        return None
    match = _XMLTV_TIME.fullmatch(value.strip())
    if not match or not match.group(2):
        return None
    try:
        return datetime.strptime(" ".join(match.groups()), "%Y%m%d%H%M%S %z").astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def parse_xmltv(payload: bytes, *, limit: int = MAX_PROGRAMMES) -> list[dict]:
    """Return normalized programmes, with bounded input and no external entities."""
    if len(payload) > MAX_XML_SIZE:
        raise ValueError("XMLTV feed exceeds maximum size")
    if b"\x00" in payload:
        raise ValueError("XMLTV must use an ASCII-compatible encoding")
    if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise ValueError("DTD and entity definitions are not supported")
    results: list[dict] = []
    for _event, element in ET.iterparse(BytesIO(payload), events=("end",)):
        if element.tag != "programme":
            continue
        channel = element.attrib.get("channel", "").strip()
        start = parse_xmltv_time(element.attrib.get("start"))
        stop = parse_xmltv_time(element.attrib.get("stop"))
        if channel and start and stop and stop > start:
            title_node = element.find("title")
            desc_node = element.find("desc")
            title = "".join(title_node.itertext()).strip()[:300] if title_node is not None else ""
            desc = "".join(desc_node.itertext()).strip()[:2000] if desc_node is not None else ""
            if title:
                results.append({
                    "channel": channel[:160],
                    "start": start.isoformat(),
                    "stop": stop.isoformat(),
                    "title": title,
                    "description": desc,
                    "subtitle": (element.findtext("sub-title") or "")[:300],
                    "category": (element.findtext("category") or "")[:160],
                })
        element.clear()
        if len(results) >= min(limit, MAX_PROGRAMMES):
            break
    return results
