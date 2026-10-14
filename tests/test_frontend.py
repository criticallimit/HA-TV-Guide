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

class FrontendTests(unittest.IsolatedAsyncioTestCase):
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
