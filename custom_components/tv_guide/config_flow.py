"""Config flow for TV Guide."""

from typing import Any

import voluptuous as vol

from homeassistant import config_entries

DOMAIN = "tv_guide"


class TVGuideConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Initial setup-only TV Guide flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Create a preliminary entry for manual discovery testing."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title="TV Guide", data={})
        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))
