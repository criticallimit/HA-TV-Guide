"""Automatic initial settings from the Home Assistant installation."""
from .country_sources import COUNTRY_FEEDS

LANGUAGES = {"de", "en", "da", "nl", "fr", "it", "nb", "sv"}
LANGUAGE_COUNTRIES = {"de": "de", "en": "gb", "da": "dk", "nl": "nl", "fr": "fr", "nb": "no", "sv": "se"}


def installation_defaults(config):
    """Use HA's country first; fall back for unsupported regions without a form."""
    language = str(getattr(config, "language", "") or "en").lower().replace("_", "-").split("-")[0]
    if language == "no":
        language = "nb"
    if language not in LANGUAGES:
        language = "en"
    country = str(getattr(config, "country", "") or "").lower()
    if country == "uk":
        country = "gb"
    if country not in COUNTRY_FEEDS:
        country = LANGUAGE_COUNTRIES.get(language, "de")
    return {"country": country, "language": language, "backend_mode": "original",
            "channels": [], "notification_service": "persistent_notification.create"}
