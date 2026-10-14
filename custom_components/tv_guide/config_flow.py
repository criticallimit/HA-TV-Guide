"""Install TV Guide automatically using Home Assistant's locale."""
from homeassistant import config_entries

from .const import DOMAIN
from .ha_defaults import installation_defaults


class TVGuideConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Create one native guide without an input form."""

    VERSION = 2

    async def async_step_user(self, user_input=None):
        """Selecting the integration is enough to configure it."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title="TV Guide", data=installation_defaults(self.hass.config))
