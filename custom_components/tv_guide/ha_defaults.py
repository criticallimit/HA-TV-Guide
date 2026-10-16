"""Automatic initial settings from the Home Assistant installation."""
from .countries import COUNTRIES, COUNTRY_ALIASES, LANGUAGE_COUNTRIES

from .languages import normalize_language


def installation_defaults(config):
    """Use HA's country first; fall back for unsupported regions without a form."""
    language = normalize_language(getattr(config, "language", ""))
    country = str(getattr(config, "country", "") or "").lower()
    country = COUNTRY_ALIASES.get(country, country)
    if country not in COUNTRIES:
        country = LANGUAGE_COUNTRIES.get(language, "de")
    return {"country": country, "language": language,
            "channels": [], "notification_service": "persistent_notification.create"}
