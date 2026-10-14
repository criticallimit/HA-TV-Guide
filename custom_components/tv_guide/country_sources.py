"""Baseline XMLTV sources matching the existing TV Guide country definitions.

These are publicly reachable feed *locations*, not guarantees of licensing,
coverage, availability, or compatibility with the current download limit.
"""

COUNTRY_FEEDS = {
    "de": "https://www.open-epg.com/files/germany.xml.gz",
    "at": "https://www.open-epg.com/files/austria.xml.gz",
    "ch": "https://www.open-epg.com/files/switzerland2.xml.gz",
    "nl": "https://www.open-epg.com/files/netherlands.xml.gz",
    "be": "https://www.open-epg.com/files/belgium.xml.gz",
    "dk": "https://www.open-epg.com/files/denmark.xml.gz",
    "no": "https://www.open-epg.com/files/norway.xml.gz",
    "fr": "https://www.open-epg.com/files/france.xml.gz",
    "se": "https://www.open-epg.com/files/sweden1.xml.gz",
    "gb": "https://www.open-epg.com/files/unitedkingdom.xml.gz",
}

# Only alternatives already configured in the reference add-on.
COUNTRY_FALLBACKS = {
    "de": ("https://epgshare01.online/epgshare01/epg_ripper_DE1.xml.gz",),
    "gb": ("https://epgshare01.online/epgshare01/epg_ripper_UK1.xml.gz",),
}


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
