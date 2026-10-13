"""Bounded async XMLTV download for explicitly configured HTTPS feed URLs."""

from __future__ import annotations

import gzip
from urllib.parse import urlsplit

from aiohttp import ClientError, ClientSession, ClientTimeout

from .xmltv import MAX_XML_SIZE, parse_xmltv

MAX_WIRE_BYTES = 12 * 1024 * 1024


def validate_feed_url(url: str) -> str:
    """Accept only fully qualified HTTPS URLs without credentials."""
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Enter an HTTPS XMLTV feed URL without credentials or fragments")
    return url


async def fetch_programmes(session: ClientSession, url: str) -> list[dict]:
    """Download once with strict limits, then parse off the event loop via caller."""
    validate_feed_url(url)
    try:
        async with session.get(url, timeout=ClientTimeout(total=60), allow_redirects=False) as response:
            response.raise_for_status()
            data = bytearray()
            async for part in response.content.iter_chunked(65536):
                data.extend(part)
                if len(data) > MAX_WIRE_BYTES:
                    raise ValueError("XMLTV download is too large")
    except ClientError as exc:
        raise ConnectionError("XMLTV download failed") from exc
    payload = bytes(data)
    if payload.startswith(b"\x1f\x8b"):
        with gzip.GzipFile(fileobj=__import__("io").BytesIO(payload)) as stream:
            payload = stream.read(MAX_XML_SIZE + 1)
    if len(payload) > MAX_XML_SIZE:
        raise ValueError("Decompressed XMLTV feed is too large")
    return payload
