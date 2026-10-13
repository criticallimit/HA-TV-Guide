"""Async EPG coordinator for an opt-in external XMLTV feed."""

from datetime import timedelta

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .epg_client import decompress_feed, fetch_programmes
from .xmltv import parse_xmltv


class TVGuideEPGCoordinator(DataUpdateCoordinator[list[dict]]):
    """Maintain one shared EPG snapshot, refreshing at most every 3 hours."""

    def __init__(self, hass, url: str):
        super().__init__(
            hass,
            logger=__import__("logging").getLogger(__name__),
            name="TV Guide EPG",
            update_interval=timedelta(hours=3),
        )
        self.url = url

    async def _async_update_data(self) -> list[dict]:
        try:
            payload = await fetch_programmes(async_get_clientsession(self.hass), self.url)
            decoded = await self.hass.async_add_executor_job(decompress_feed, payload)
            return await self.hass.async_add_executor_job(parse_xmltv, decoded)
        except Exception as exc:
            raise UpdateFailed(f"EPG update failed: {type(exc).__name__}") from exc
