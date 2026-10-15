"""Response action adapters validate writes and read the guide snapshot only."""
import importlib.util
from datetime import datetime,timedelta,timezone
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
vol.In=lambda choices:choices
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

    async def test_empty_guide_snapshot_has_sender_model_without_epg_requests(self):
        result=await self.call('get_guide')
        self.assertTrue(result['channels'])
        self.assertTrue(all(item['programs']==[] for item in result['channels']))
        self.assertEqual(result['country'],'de')
        self.assertEqual(result['main_channel_ids'][0],'ard')
        choices=await self.call('get_personal_channels')
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
        with self.assertRaises(exc.HomeAssistantError):await self.call('get_guide',{'at':'2026-10-14T20:15:00'})
        self.assertEqual(self.updates,[])

    async def test_unload_removes_all_guide_ui_actions(self):
        adapter.async_remove_ui_services(self.hass)
        self.assertEqual(self.handlers,{})

    async def test_preparation_progress_and_retry_use_owned_runtime(self):
        calls=[]
        status={'first_install':True,'complete':False,'logos':{'total':37},'programmes':{'running':False,'ready':False,'error':False}}
        backend=types.SimpleNamespace(preparation_status=lambda:dict(status),start_logo_download=lambda force:calls.append(('logos',force)))
        async def request(*args):calls.append(args)
        self.hass.data['tv_guide']={'entry':types.SimpleNamespace(is_multi_source=True,backend=backend,refresh_running=False,async_guide_request=request)}
        self.assertEqual(await self.call('get_preparation_status'),status)
        self.assertEqual(calls,[])
        await self.call('retry_preparation')
        self.assertEqual(calls,[('logos',True),('refresh',)])

    async def test_logo_retry_does_not_redownload_healthy_programmes(self):
        calls=[]
        status={'complete':False,'logos':{'error':True},'programmes':{'running':False,'ready':True,'error':False}}
        backend=types.SimpleNamespace(preparation_status=lambda:dict(status),start_logo_download=lambda force:calls.append(force))
        async def request(*args):self.fail('Unnecessary programme refresh')
        self.hass.data['tv_guide']={'entry':types.SimpleNamespace(is_multi_source=True,backend=backend,async_guide_request=request)}
        await self.call('retry_preparation')
        self.assertEqual(calls,[True])

    async def test_custom_feed_does_not_need_logo_preparation(self):
        self.assertEqual(await self.call('get_preparation_status'),{'complete':True,'first_install':False})

    async def test_original_guide_action_honours_at_without_truncating_default_timelines(self):
        at=datetime(2030,1,1,tzinfo=timezone.utc)
        rows=[{'id':str(i),'title':str(i),'start':(at+timedelta(hours=i)).isoformat(),'end':(at+timedelta(hours=i+1)).isoformat(),'icon':'artwork'} for i in range(-2,9)]
        guide={'country':'de','channels':[{'id':'ard','logo':'original','programs':rows}]}
        async def request(*args):return guide
        self.hass.data['tv_guide']={'entry':types.SimpleNamespace(is_multi_source=True,async_guide_request=request)}
        window=await self.call('get_guide',{'at':at.isoformat()})
        self.assertEqual([item['id'] for item in window['channels'][0]['programs']],[str(i) for i in range(7)])
        self.assertEqual(window['channels'][0]['logo'],'original')
        self.assertEqual(window['channels'][0]['programs'][0]['icon'],'artwork')
        self.assertEqual(len((await self.call('get_guide'))['channels'][0]['programs']),11)
        self.assertEqual(len(guide['channels'][0]['programs']),11)

    async def test_original_guide_rejects_invalid_timestamp_before_dispatch(self):
        calls=[]
        async def request(*args):calls.append(args);return {}
        self.hass.data['tv_guide']={'entry':types.SimpleNamespace(is_multi_source=True,async_guide_request=request)}
        for at in ('bad','2030-01-01T12:00:00','9999-12-31T23:30:00-01:00'):
            with self.assertRaises(exc.HomeAssistantError):await self.call('get_guide',{'at':at})
        self.assertEqual(calls,[])

    async def test_original_settings_persist_normalized_values_and_notification_destination(self):
        settings={'country':'at','language':'de','default_view':'now','columns_desktop':5,'max_channels':0,'theme_mode':'auto','refresh_minutes':180,'notification_service':'persistent_notification.create'}
        async def request(endpoint,method='GET',body=None):
            if method=='POST':
                settings.update(body)
                settings['country']=settings['country'].lower()
                return {'ok':True}
            return dict(settings)
        scheduler=types.SimpleNamespace(notification_service='persistent_notification.create')
        self.hass.data['tv_guide']={'entry':types.SimpleNamespace(is_multi_source=True,async_guide_request=request)}
        self.hass.data['tv_guide_reminder_schedulers']={'entry':scheduler}
        adapter.async_register_ui_services(self.hass)
        await self.call('set_ui_settings',{'options':{'country':'AT','notification_service':'notify.mobile_app_test'}})
        self.assertEqual(self.entry.options['country'],'at')
        self.assertEqual(scheduler.notification_service,'notify.mobile_app_test')
        self.assertNotIn('backend_mode',self.entry.options)
        with self.assertRaises(exc.HomeAssistantError):
            await self.call('set_ui_settings',{'options':{'notification_service':'shell.execute'}})
        self.assertEqual(scheduler.notification_service,'notify.mobile_app_test')

if __name__=='__main__':unittest.main()
