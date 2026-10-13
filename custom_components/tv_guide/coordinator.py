"""Async EPG coordinator for an opt-in external XMLTV feed."""

from datetime import datetime, timedelta, timezone
import logging

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .epg_client import decompress_feed, fetch_programmes
from .secure_transport import public_epg_session
from .xmltv import parse_xmltv
from .channel_catalog import parse_channel_catalog
from .catalogs import resolve_catalogue_channels


class TVGuideEPGCoordinator(DataUpdateCoordinator[list[dict]]):
    """Maintain one shared EPG snapshot, refreshing at most every 3 hours."""

    def __init__(self, hass, url: str, country: str = ""):
        super().__init__(
            hass,
            logger=logging.getLogger(__name__),
            name="TV Guide EPG",
            update_interval=timedelta(hours=3),
        )
        self.url = url
        self.country = country
        self.last_successful_refresh: datetime | None = None
        self.canonical_channels: list[dict] = []
        self.channels: list[dict[str, str]] = []

    async def _async_update_data(self) -> list[dict]:
        try:
            async with public_epg_session() as session:
                payload = await fetch_programmes(session, self.url)
            decoded = await self.hass.async_add_executor_job(decompress_feed, payload)
            programmes = await self.hass.async_add_executor_job(parse_xmltv, decoded)
            channels = await self.hass.async_add_executor_job(parse_channel_catalog, decoded)
            canonical_channels = await self.hass.async_add_executor_job(
                resolve_catalogue_channels, self.country, channels
            )
            self.channels = channels
            self.canonical_channels = canonical_channels
            self.last_successful_refresh = datetime.now(timezone.utc)
            return programmes
        except Exception as exc:
            raise UpdateFailed(f"EPG update failed: {type(exc).__name__}") from exc
