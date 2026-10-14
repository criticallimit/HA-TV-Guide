"""Config and options flows for the experimental TV Guide integration."""

from typing import Any

import voluptuous as vol

from homeassistant import config_entries

from .const import DOMAIN
from .feed_url import validate_feed_url
from .country_sources import COUNTRY_FEEDS
from .channel_selection import parse_channel_selection

CONF_FEED_URL = "feed_url"
CONF_COUNTRY = "country"
CONF_CHANNELS = "channels"
CONF_NOTIFICATION_SERVICE = "notification_service"
COUNTRY_OPTIONS = {"": "No predefined country", **{code: code.upper() for code in COUNTRY_FEEDS}}


def _feed_schema(current_url: str = "", current_country: str = "", current_channels: str = "", current_notification_service: str = "persistent_notification.create") -> vol.Schema:
    """Allow an empty URL to continue using only the add-on bridge."""
    return vol.Schema({
        vol.Optional(CONF_COUNTRY, default=current_country): vol.In(COUNTRY_OPTIONS),
        vol.Optional(CONF_FEED_URL, default=current_url): str,
        vol.Optional(CONF_CHANNELS, default=current_channels): str,
        vol.Optional(CONF_NOTIFICATION_SERVICE, default=current_notification_service): str,
    })


def _validated_feed(user_input: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    """Normalize config input without starting any network request."""
    url = user_input.get(CONF_FEED_URL, "").strip()
    country = user_input.get(CONF_COUNTRY, "")
    if country not in COUNTRY_OPTIONS:
        return {}, {CONF_COUNTRY: "invalid_country"}
    try:
        selected = parse_channel_selection(user_input.get(CONF_CHANNELS, ""))
    except ValueError:
        return {}, {CONF_CHANNELS: "invalid_channels"}
    notification_service = user_input.get(CONF_NOTIFICATION_SERVICE, "persistent_notification.create").strip()
    if notification_service != "persistent_notification.create" and not (notification_service.startswith("notify.") and bool(notification_service[7:]) and notification_service[7:].isascii() and notification_service[7:].replace("_", "").isalnum()):
        return {}, {CONF_NOTIFICATION_SERVICE: "invalid_notification_service"}
    data = {CONF_COUNTRY: country, CONF_FEED_URL: "", CONF_CHANNELS: selected, CONF_NOTIFICATION_SERVICE: notification_service}
    if not url:
        return data, {}
    try:
        validate_feed_url(url)
    except ValueError:
        return {}, {CONF_FEED_URL: "invalid_url"}
    return {**data, CONF_FEED_URL: url}, {}


class TVGuideConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure a single TV Guide instance."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry):
        """Provide an options form for changing the feed after installation."""
        return TVGuideOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Accept an optional HTTPS XMLTV feed URL."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        errors: dict[str, str] = {}
        if user_input is not None:
            data, errors = _validated_feed(user_input)
            if not errors:
                return self.async_create_entry(title="TV Guide", data=data)
        return self.async_show_form(
            step_id="user", data_schema=_feed_schema(), errors=errors
        )


class TVGuideOptionsFlow(config_entries.OptionsFlow):
    """Allow changing the feed without reinstalling the integration."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Validate and save the optional XMLTV feed URL."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data, errors = _validated_feed(user_input)
            if not errors:
                return self.async_create_entry(title="", data=data)
        current = self.config_entry.options.get(
            CONF_FEED_URL, self.config_entry.data.get(CONF_FEED_URL, "")
        )
        country = self.config_entry.options.get(
            CONF_COUNTRY, self.config_entry.data.get(CONF_COUNTRY, "")
        )
        channels = self.config_entry.options.get(
            CONF_CHANNELS, self.config_entry.data.get(CONF_CHANNELS, [])
        )
        notification_service = self.config_entry.options.get(
            CONF_NOTIFICATION_SERVICE, self.config_entry.data.get(CONF_NOTIFICATION_SERVICE, "persistent_notification.create")
        )
        return self.async_show_form(
            step_id="init", data_schema=_feed_schema(current, country, ", ".join(channels) if isinstance(channels, list) else channels, notification_service), errors=errors
        )
