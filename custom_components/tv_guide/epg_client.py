"""Bounded async XMLTV download for explicitly configured HTTPS feed URLs."""

from __future__ import annotations

import gzip
from io import BytesIO
from urllib.parse import urlsplit

from aiohttp import ClientError, ClientSession, ClientTimeout

from .xmltv import MAX_XML_SIZE

MAX_WIRE_BYTES = 12 * 1024 * 1024


def validate_feed_url(url: str) -> str:
    """Accept only fully qualified HTTPS URLs without credentials."""
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Enter an HTTPS XMLTV feed URL without credentials or fragments")
    return url


async def fetch_programmes(session: ClientSession, url: str) -> bytes:
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
    return bytes(data)


def decompress_feed(payload: bytes) -> bytes:
    """Bound decompressed data; call in Home Assistant's executor."""
    if payload.startswith(b"\x1f\x8b"):
        with gzip.GzipFile(fileobj=BytesIO(payload)) as stream:
            payload = stream.read(MAX_XML_SIZE + 1)
    if len(payload) > MAX_XML_SIZE:
        raise ValueError("Decompressed XMLTV feed is too large")
    return payload
