"""Feed URL policy for an opt-in external XMLTV source.

Network-layer DNS resolution must additionally reject private/reserved targets
before this downloader is enabled in a config flow.
"""

import ipaddress
from urllib.parse import urlsplit


def validate_feed_url(url: str) -> str:
    """Reject unsafe URL syntax and obvious non-public destinations."""
    if not isinstance(url, str) or len(url) > 2048 or any(ord(c) < 33 for c in url):
        raise ValueError("Invalid feed URL")
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Invalid feed URL") from exc
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or port not in (None, 443)
        or hostname.lower() == "localhost"
        or hostname.lower().endswith((".localhost", ".local", ".internal"))
    ):
        raise ValueError("Feed must be a public HTTPS URL on port 443")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        if "." not in hostname or hostname.startswith(".") or hostname.endswith("."):
            raise ValueError("Feed host must be a public domain name") from None
    else:
        if not address.is_global:
            raise ValueError("Private and reserved addresses are not accepted")
    return url
