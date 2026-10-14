"""Serve the bundled native card without copying files into /config/www."""
import asyncio
from pathlib import Path

from homeassistant.components.http import StaticPathConfig

from .const import DOMAIN

CARD_URL = "/tv_guide/frontend/tv-guide-native-card.js"


async def async_register_frontend(hass):
    """Register public static code once per HA process, including across reloads."""
    lock = hass.data.setdefault(DOMAIN + "_frontend_lock", asyncio.Lock())
    async with lock:
        if hass.data.get(DOMAIN + "_frontend_registered"):
            return
        await hass.http.async_register_static_paths([
            StaticPathConfig(
                "/tv_guide/frontend", str(Path(__file__).parent / "frontend"), False
            )
        ])
        hass.data[DOMAIN + "_frontend_registered"] = True
