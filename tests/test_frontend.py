"""Bundled frontend registration is retryable and idempotent across entry reloads."""
import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
from dataclasses import dataclass

ROOT=Path(__file__).resolve().parents[1]/'custom_components'/'tv_guide'
PKG='_tvguide_frontend_tests'
pkg=types.ModuleType(PKG);pkg.__path__=[str(ROOT)]
http=types.ModuleType('homeassistant.components.http')
@dataclass
class StaticPathConfig:
    url_path:str
    path:str
    cache_headers:bool
http.StaticPathConfig=StaticPathConfig
ui=types.ModuleType('homeassistant.components.frontend')
ui.add_extra_js_url=lambda hass,url:hass.data.setdefault('modules',set()).add(url)
ui.remove_extra_js_url=lambda hass,url:hass.data['modules'].remove(url)
ui.async_register_built_in_panel=lambda hass,name,**kwargs:hass.data.setdefault('panels',{}).update({kwargs['frontend_url_path']:kwargs})
ui.async_remove_panel=lambda hass,path:hass.data['panels'].pop(path)
components=types.ModuleType('homeassistant.components');components.frontend=ui
logo=types.ModuleType(PKG+'.logo_view');logo.TVGuideLogoView=lambda hass:object()
async def executor(fn,*args):return fn(*args)
with patch.dict(sys.modules,{PKG:pkg,PKG+'.logo_view':logo,'homeassistant.components':components,'homeassistant.components.frontend':ui,'homeassistant.components.http':http}):
    for name in ('const','frontend'):
        spec=importlib.util.spec_from_file_location(PKG+'.'+name,ROOT/(name+'.py'))
        module=importlib.util.module_from_spec(spec)
        sys.modules[spec.name]=module
        spec.loader.exec_module(module)
frontend=module

class Resources:
    """Model HA's lazy storage collection, including its websocket field names."""
    def __init__(self, persisted=()):
        self.persisted = list(persisted)
        self.items = []
        self.loaded = False
        self.created = 0
    async def async_get_info(self):
        if not self.loaded:
            self.items = [dict(item) for item in self.persisted]
            self.loaded = True
        return {"resources": len(self.items)}
    def async_items(self):
        return self.items
    async def async_create_item(self, values):
        self.created += 1
        self.items.append({"id": str(self.created), "url": values["url"], "type": values["res_type"]})
    async def async_update_item(self, item_id, values):
        item = next(item for item in self.items if item["id"] == item_id)
        item.update(url=values["url"], type=values["res_type"])

class FrontendTests(unittest.IsolatedAsyncioTestCase):
    async def test_dashboard_resource_survives_reload_and_fresh_process(self):
        resources = Resources()
        async def register(paths):
            pass
        def new_hass(collection):
            return types.SimpleNamespace(
                data={"lovelace": types.SimpleNamespace(resources=collection)},
                async_add_executor_job=executor,
                http=types.SimpleNamespace(async_register_static_paths=register, register_view=lambda view: None))
        hass = new_hass(resources)
        await asyncio.gather(frontend.async_register_frontend(hass), frontend.async_register_frontend(hass))
        self.assertEqual(resources.created, 1)
        self.assertEqual(resources.items[0]["url"], frontend.MODULE_URL)
        self.assertEqual(resources.items[0]["type"], "module")
        frontend.async_remove_frontend(hass)
        self.assertEqual(len(resources.items), 1)
        await frontend.async_register_frontend(hass)
        self.assertEqual(resources.created, 1)
        restarted = Resources(resources.items)
        await frontend.async_register_frontend(new_hass(restarted))
        self.assertTrue(restarted.loaded)
        self.assertEqual(restarted.created, 0)
        self.assertEqual(len(restarted.items), 1)

    async def test_dashboard_resource_upgrades_existing_url_and_type(self):
        unrelated = {"id": "other", "url": "/other-card.js", "type": "module"}
        resources = Resources([unrelated, {"id": "guide", "url": frontend.CARD_URL + "?v=old", "type": "js"}])
        hass = types.SimpleNamespace(data={"lovelace": {"resources": resources}})
        await frontend._async_register_dashboard_resource(hass)
        self.assertEqual(resources.items[0], unrelated)
        self.assertEqual(resources.items[1], {"id": "guide", "url": frontend.MODULE_URL, "type": "module"})
        self.assertEqual(resources.created, 0)

    async def test_yaml_resources_remain_user_managed(self):
        items = [{"url": "/user-card.js", "type": "module"}]
        resources = types.SimpleNamespace(async_items=lambda: items)
        hass = types.SimpleNamespace(data={"lovelace": types.SimpleNamespace(resources=resources)})
        await frontend._async_register_dashboard_resource(hass)
        self.assertEqual(items, [{"url": "/user-card.js", "type": "module"}])

    async def test_concurrent_registration_and_reload_register_only_once(self):
        calls=[]
        async def register(paths):
            await asyncio.sleep(0)
            calls.extend(paths)
        views=[]
        hass=types.SimpleNamespace(data={},async_add_executor_job=executor,http=types.SimpleNamespace(async_register_static_paths=register,register_view=views.append))
        await asyncio.gather(frontend.async_register_frontend(hass),frontend.async_register_frontend(hass))
        await frontend.async_register_frontend(hass)
        self.assertEqual(len(calls),1)
        self.assertEqual(len(views),1)
        self.assertEqual(calls[0].url_path,'/tv_guide/frontend')
        self.assertTrue((Path(calls[0].path)/'tv-guide-card.js').is_file())
        self.assertFalse(calls[0].cache_headers)
        self.assertIn(frontend.MODULE_URL,hass.data['modules'])
        self.assertIn(frontend.PANEL_PATH,hass.data['panels'])
        frontend.async_remove_frontend(hass)
        self.assertEqual(hass.data['panels'],{})
        self.assertEqual(hass.data['modules'],set())
        await frontend.async_register_frontend(hass)
        self.assertEqual(len(calls),1)
        self.assertIn(frontend.PANEL_PATH,hass.data['panels'])

    async def test_registration_failure_does_not_prevent_retry(self):
        attempts=[]
        async def register(paths):
            attempts.append(paths)
            if len(attempts)==1:
                raise OSError('HTTP registration failure')
        views=[]
        hass=types.SimpleNamespace(data={},async_add_executor_job=executor,http=types.SimpleNamespace(async_register_static_paths=register,register_view=views.append))
        with self.assertRaises(OSError):
            await frontend.async_register_frontend(hass)
        await frontend.async_register_frontend(hass)
        self.assertEqual(len(attempts),2)
        self.assertEqual(len(views),1)

if __name__=='__main__':
    unittest.main()
