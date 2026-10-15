"""Serve public packaged artwork without exposing integration data or storage."""
from aiohttp import web
from zipfile import BadZipFile
from homeassistant.components.http import HomeAssistantView
from .logo_assets import bundled_logo_library


class TVGuideLogoView(HomeAssistantView):
    url='/tv_guide/logo/{source:.+}'
    name='tv_guide:logo'
    requires_auth=False

    def __init__(self, hass):
        self._hass=hass
        self.library=bundled_logo_library()

    async def get(self, request, source):
        if not self.library.contains(source):
            return web.Response(status=404)
        try:
            data,mime=await self._hass.async_add_executor_job(self.library.render,source,request.query.get('normalize')=='1')
        except (KeyError,OSError,ValueError,BadZipFile):
            return web.Response(status=404, headers={'Cache-Control':'no-store'})
        return web.Response(body=data,content_type=mime,headers={'Cache-Control':'public, max-age=86400','X-Content-Type-Options':'nosniff'})
