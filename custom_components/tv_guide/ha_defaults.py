"""Automatic initial settings from the Home Assistant installation."""
from .countries import COUNTRIES, COUNTRY_ALIASES, LANGUAGE_COUNTRIES

LANGUAGES = {"de", "en", "da", "nl", "fr", "it", "nb", "sv"}


def installation_defaults(config):
    """Use HA's country first; fall back for unsupported regions without a form."""
    language = str(getattr(config, "language", "") or "en").lower().replace("_", "-").split("-")[0]
    if language == "no":
        language = "nb"
    if language not in LANGUAGES:
        language = "en"
    country = str(getattr(config, "country", "") or "").lower()
    country = COUNTRY_ALIASES.get(country, country)
    if country not in COUNTRIES:
        country = LANGUAGE_COUNTRIES.get(language, "de")
    return {"country": country, "language": language,
            "channels": [], "notification_service": "persistent_notification.create"}
