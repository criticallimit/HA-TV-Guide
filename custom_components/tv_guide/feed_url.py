"""Feed URL policy for an opt-in external XMLTV source.

The dedicated transport also rejects private/reserved DNS answers when opening
the connection; URL validation alone is insufficient.
"""

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
    # IP literals can bypass aiohttp's DNS resolver entirely.
    # Require DNS hostnames until peer-address verification is implemented.
    if "." not in hostname or hostname.startswith(".") or hostname.endswith("."):
        raise ValueError("Feed host must be a public DNS hostname")
    if ":" in hostname or all(part.isdecimal() for part in hostname.split(".")):
        raise ValueError("Literal IP addresses are not permitted")
    return url
