"""Baseline XMLTV sources matching the existing TV Guide country definitions.

These are publicly reachable feed *locations*, not guarantees of licensing,
coverage, availability, or compatibility with the current download limit.
"""

from .countries import COUNTRY_FEEDS, COUNTRY_FALLBACKS


def effective_feed(config: dict) -> str | None:
    """Manual URL overrides country baseline; otherwise no EPG fetch."""
    manual = config.get("feed_url")
    if manual:
        return manual
    return COUNTRY_FEEDS.get(config.get("country", ""))


def feed_candidates(config: dict) -> tuple[str, ...]:
    """Return ordered country sources; an explicit custom URL stands alone."""
    primary = effective_feed(config)
    if not primary:
        return ()
    if config.get("feed_url"):
        return (primary,)
    return (primary, *COUNTRY_FALLBACKS.get(config.get("country", ""), ()))
