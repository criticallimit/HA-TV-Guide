"""Config and options flows for the experimental TV Guide integration."""

from typing import Any

import voluptuous as vol

from homeassistant import config_entries

from .const import DOMAIN
from .feed_url import validate_feed_url

CONF_FEED_URL = "feed_url"


def _feed_schema(current_url: str = "") -> vol.Schema:
    """Allow an empty URL to continue using only the add-on bridge."""
    return vol.Schema({vol.Optional(CONF_FEED_URL, default=current_url): str})


def _validated_feed(user_input: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    """Normalize config input without starting any network request."""
    url = user_input.get(CONF_FEED_URL, "").strip()
    if not url:
        return {}, {}
    try:
        validate_feed_url(url)
    except ValueError:
        return {}, {CONF_FEED_URL: "invalid_url"}
    return {CONF_FEED_URL: url}, {}


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
        return self.async_show_form(
            step_id="init", data_schema=_feed_schema(current), errors=errors
        )
