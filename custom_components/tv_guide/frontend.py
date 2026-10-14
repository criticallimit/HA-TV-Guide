"""Serve the bundled native card without copying files into /config/www."""
import asyncio
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.components import frontend

from .const import DOMAIN

CARD_URL = "/tv_guide/frontend/tv-guide-native-card.js"
MODULE_URL = CARD_URL + "?v=4"
PANEL_PATH = "tv-guide-native"


async def async_register_frontend(hass):
    """Register public static code once per HA process, including across reloads."""
    lock = hass.data.setdefault(DOMAIN + "_frontend_lock", asyncio.Lock())
    async with lock:
        if not hass.data.get(DOMAIN + "_frontend_registered"):
            await hass.http.async_register_static_paths([
                StaticPathConfig("/tv_guide/frontend", str(Path(__file__).parent / "frontend"), False)
            ])
            hass.data[DOMAIN + "_frontend_registered"] = True
        if not hass.data.get(DOMAIN + "_panel_registered"):
            frontend.async_register_built_in_panel(hass, "custom", sidebar_title="TV Guide",
                sidebar_icon="mdi:television-guide", frontend_url_path=PANEL_PATH,
                config={"_panel_custom":{"name":"tv-guide-native-panel",
                    "module_url":"/tv_guide/frontend/tv-guide-native-panel.js?v=4",
                    "embed_iframe":False,"trust_external":False}})
            hass.data[DOMAIN + "_panel_registered"] = True
        frontend.add_extra_js_url(hass, MODULE_URL)


def async_remove_frontend(hass):
    """Remove owned UI registrations when the last entry unloads."""
    if hass.data.pop(DOMAIN + "_panel_registered", False):
        frontend.async_remove_panel(hass, PANEL_PATH)
        frontend.remove_extra_js_url(hass, MODULE_URL)
