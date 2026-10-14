"""Response action adapters validate writes and read the native snapshot only."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]/'custom_components'/'tv_guide'
PKG='_tvguide_ui_services_tests'
pkg=types.ModuleType(PKG);pkg.__path__=[str(ROOT)]
core=types.ModuleType('homeassistant.core');core.SupportsResponse=types.SimpleNamespace(ONLY='only')
exc=types.ModuleType('homeassistant.exceptions');exc.HomeAssistantError=type('HomeAssistantError',(Exception,),{})
vol=types.ModuleType('voluptuous');vol.Schema=lambda value:value;vol.Required=vol.Optional=lambda key,**kwargs:key
with patch.dict(sys.modules,{PKG:pkg,'homeassistant.core':core,'homeassistant.exceptions':exc,'voluptuous':vol}):
    for name in ('const','catalogs','ui_payload','ui_services'):
        spec=importlib.util.spec_from_file_location(PKG+'.'+name,ROOT/(name+'.py'))
        module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    adapter=module

class UIServicesTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.handlers={};self.entry=types.SimpleNamespace(entry_id='entry',data={'country':'de'},options={})
        self.updates=[]
        async def executor(fn,*args):return fn(*args)
        def update(entry,**kwargs):entry.options=kwargs['options'];self.updates.append(entry.options)
        self.hass=types.SimpleNamespace(data={'tv_guide_saved':{'entry':object()}},config=types.SimpleNamespace(time_zone='Europe/Berlin'),async_add_executor_job=executor,
            config_entries=types.SimpleNamespace(async_get_entry=lambda key:self.entry,async_update_entry=update),
            services=types.SimpleNamespace(async_register=lambda domain,name,fn,**kwargs:self.handlers.update({name:fn}),async_remove=lambda domain,name:self.handlers.pop(name,None)))
        adapter.async_register_ui_services(self.hass)

    async def call(self,name,data=None):return await self.handlers[name](types.SimpleNamespace(service=name,data=data or {}))

    async def test_bridge_only_has_original_sender_model_and_no_epg_requests(self):
        result=await self.call('get_native_guide')
        self.assertTrue(result['channels'])
        self.assertTrue(all(item['programs']==[] for item in result['channels']))
        self.assertEqual(result['country'],'de')
        self.assertEqual(result['main_channel_ids'][0],'ard')
        choices=await self.call('get_native_channels')
        self.assertEqual(choices['order'][0],'ard')

    async def test_validated_display_settings_persist_without_replacing_other_options(self):
        self.entry.options={'channels':['ard'],'feed_url':'https://example.org/feed.xml'}
        result=await self.call('set_ui_settings',{'options':{'columns_desktop':4,'language':'en','notification_service':'notify.mobile_app_test'}})
        self.assertTrue(result['ok'])
        self.assertEqual(self.entry.options['channels'],['ard'])
        self.assertEqual(self.entry.options['feed_url'],'https://example.org/feed.xml')
        self.assertEqual((await self.call('get_ui_settings'))['columns_desktop'],4)

    async def test_invalid_settings_and_naive_query_do_not_mutate_entry(self):
        with self.assertRaises(exc.HomeAssistantError):await self.call('set_ui_settings',{'options':{'notification_service':'shell.execute'}})
        with self.assertRaises(exc.HomeAssistantError):await self.call('get_native_guide',{'at':'2026-10-14T20:15:00'})
        self.assertEqual(self.updates,[])

    async def test_unload_removes_all_native_ui_actions(self):
        adapter.async_remove_ui_services(self.hass)
        self.assertEqual(self.handlers,{})

if __name__=='__main__':unittest.main()
