"""Config flow for the experimental TV Guide integration."""

from typing import Any

import voluptuous as vol

from homeassistant import config_entries

from .const import DOMAIN
from .feed_url import validate_feed_url

CONF_FEED_URL = "feed_url"


class TVGuideConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure a single TV Guide instance."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Accept an optional HTTPS XMLTV feed URL."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        errors: dict[str, str] = {}
        if user_input is not None:
            url = user_input.get(CONF_FEED_URL, "").strip()
            if url:
                try:
                    validate_feed_url(url)
                except ValueError:
                    errors[CONF_FEED_URL] = "invalid_url"
                else:
                    return self.async_create_entry(title="TV Guide", data={CONF_FEED_URL: url})
            else:
                return self.async_create_entry(title="TV Guide", data={})
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Optional(CONF_FEED_URL, default=""): str}),
            errors=errors,
        )
