"""Serve the bundled TV Guide card without copying files into /config/www."""
import asyncio
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.components import frontend

from .const import DOMAIN
from .logo_view import TVGuideLogoView

CARD_URL = "/tv_guide/frontend/tv-guide-card.js"
MODULE_URL = CARD_URL + "?v=21"
PANEL_PATH = "tv-guide"


async def async_register_frontend(hass):
    """Register public static code once per HA process, including across reloads."""
    lock = hass.data.setdefault(DOMAIN + "_frontend_lock", asyncio.Lock())
    async with lock:
        if not hass.data.get(DOMAIN + "_frontend_registered"):
            if not hass.data.get(DOMAIN + "_logo_registered"):
                logo_view = await hass.async_add_executor_job(TVGuideLogoView, hass)
                hass.http.register_view(logo_view)
                hass.data[DOMAIN + "_logo_registered"] = True
            await hass.http.async_register_static_paths([
                StaticPathConfig("/tv_guide/frontend", str(Path(__file__).parent / "frontend"), False)
            ])
            hass.data[DOMAIN + "_frontend_registered"] = True
        if not hass.data.get(DOMAIN + "_panel_registered"):
            frontend.async_register_built_in_panel(hass, "custom", sidebar_title="TV Guide",
                sidebar_icon="mdi:television-guide", frontend_url_path=PANEL_PATH,
                config={"_panel_custom":{"name":"tv-guide-panel",
                    "module_url":"/tv_guide/frontend/tv-guide-panel.js?v=21",
                    "embed_iframe":False,"trust_external":False}})
            hass.data[DOMAIN + "_panel_registered"] = True
        frontend.add_extra_js_url(hass, MODULE_URL)
        await _async_register_dashboard_resource(hass)


async def _async_register_dashboard_resource(hass):
    """Let dashboards await the card module, independently of global JS loading.

    Keep the resource across entry reloads: the public static path remains
    available, and an unloaded entry must not break an existing dashboard.
    YAML resources remain user-managed; global module loading still supports
    those installations and the sidebar panel.
    """
    lovelace = hass.data.get("lovelace")
    resources = (lovelace.get("resources") if isinstance(lovelace, dict)
                 else getattr(lovelace, "resources", None))
    if resources is None or not hasattr(resources, "async_create_item"):
        return
    await resources.async_get_info()  # Load persisted items before deduplication.
    for item in resources.async_items():
        if item.get("url", "").split("?", 1)[0] == CARD_URL:
            if item["url"] != MODULE_URL or item.get("type") != "module":
                await resources.async_update_item(item["id"], {
                    "url": MODULE_URL, "res_type": "module",
                })
            return
    await resources.async_create_item({"url": MODULE_URL, "res_type": "module"})


def async_remove_frontend(hass):
    """Remove owned UI registrations when the last entry unloads."""
    if hass.data.pop(DOMAIN + "_panel_registered", False):
        frontend.async_remove_panel(hass, PANEL_PATH)
        frontend.remove_extra_js_url(hass, MODULE_URL)
