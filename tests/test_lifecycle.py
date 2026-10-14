"""Offline config-entry lifecycle tests against the public HA API surface."""
import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "tv_guide"
PKG = "_tvguide_lifecycle_tests"

class Entry:
    entry_id = "entry"
    def __init__(self, data=None):
        self.data = data or {}
        self.options = {}
        self.callbacks = []
        self.listener_removed = False
    def add_update_listener(self, listener):
        def remove():
            self.listener_removed = True
        return remove
    def async_on_unload(self, callback):
        self.callbacks.append(callback)
    # Deliberately no async_unload_callbacks: HA owns callback processing.

class Entries:
    def __init__(self):
        self.forwarded = []
        self.unloaded = []
        self.reloaded = []
        self.fail = None
        self.unload_ok = True
    async def async_forward_entry_setups(self, entry, platforms):
        self.forwarded.append(entry.entry_id)
        if self.fail:
            raise self.fail
    async def async_unload_platforms(self, entry, platforms):
        self.unloaded.append(entry.entry_id)
        return self.unload_ok
    async def async_reload(self, entry_id):
        self.reloaded.append(entry_id)

class Coordinator:
    fail = False
    def __init__(self, hass, url, country, source_urls, *, config_entry=None):
        self.url, self.country = url, country
        self.source_urls = source_urls
        self.updates = 0
    async def async_config_entry_first_refresh(self):
        if self.fail:
            raise RuntimeError("feed failure")
    def async_update_listeners(self):
        self.updates += 1

class Saved:
    def __init__(self, hass, entry_id):
        pass
    async def async_load(self):
        pass

class OriginalCoordinator(Coordinator):
    is_original=True
    def __init__(self,hass,entry,options):
        super().__init__(hass,'original-providers',options.get('country','de'),())
        self.stopped=False
    async def async_stop(self):self.stopped=True

class Scheduler:
    instances = []
    def __init__(self, hass, saved, lock, notification_service):
        self.notification_service = notification_service
        self.stopped = False
        self.scheduled = False
        self.instances.append(self)
    async def async_stop(self):
        self.stopped = True
    def reschedule(self):
        self.scheduled = True

class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        Coordinator.fail = False
        Scheduler.instances.clear()
        self.registry = set()
        self.hass = types.SimpleNamespace(data={}, config_entries=Entries(), services=types.SimpleNamespace(has_service=lambda domain,name: name in self.registry))
        self.entry = Entry()
        imports = {}
        def stub(name, **values):
            module = types.ModuleType(name)
            module.__dict__.update(values)
            imports[name] = module
        stub('homeassistant.config_entries', ConfigEntry=Entry)
        stub('homeassistant.const', Platform=types.SimpleNamespace(SENSOR='sensor', BINARY_SENSOR='binary_sensor', CALENDAR='calendar'))
        stub('homeassistant.core', HomeAssistant=object)
        stub('homeassistant.helpers', entity_registry=types.SimpleNamespace(async_get=lambda hass: types.SimpleNamespace(async_get_entity_id=lambda *args: None)))
        async def register_frontend(hass):
            pass
        stub(PKG+'.frontend', async_register_frontend=register_frontend, async_remove_frontend=lambda hass:None)
        stub(PKG+'.ha_defaults', installation_defaults=lambda config: {'country':'at','language':'de','backend_mode':'original','channels':[],'notification_service':'persistent_notification.create'})
        stub(PKG+'.ui_services', async_register_ui_services=lambda hass: self.registry.add('get_guide'), async_remove_ui_services=lambda hass: self.registry.discard('get_guide'))
        stub(PKG+'.const', DOMAIN='tv_guide')
        stub(PKG+'.coordinator', TVGuideEPGCoordinator=Coordinator)
        stub(PKG+'.original_coordinator', TVGuideOriginalCoordinator=OriginalCoordinator)
        stub(PKG+'.country_sources', effective_feed=lambda options: options.get('feed_url') or None,
             feed_candidates=lambda options: (options['feed_url'],) if options.get('feed_url') else ())
        stub(PKG+'.reminder_scheduler', TVGuideReminderScheduler=Scheduler)
        stub(PKG+'.saved_programmes', TVGuideSavedProgrammes=Saved)
        async def register_saved(hass):
            self.registry.update(['save_bookmark','get_saved_programmes'])
        stub(PKG+'.saved_services', async_register_saved_services=register_saved, async_remove_saved_services=lambda hass: self.registry.difference_update(['save_bookmark','get_saved_programmes']))
        stub(PKG+'.epg_query', async_register_epg_query=lambda hass: self.registry.add('get_programmes'), async_remove_epg_query=lambda hass: self.registry.discard('get_programmes'))
        spec = importlib.util.spec_from_file_location(PKG, ROOT/'__init__.py', submodule_search_locations=[str(ROOT)])
        self.module = importlib.util.module_from_spec(spec)
        imports[PKG] = self.module
        self.imports=patch.dict(sys.modules,imports)
        self.imports.start()
        self.addCleanup(self.imports.stop)
        spec.loader.exec_module(self.module)

    async def test_standalone_setup_without_feed_always_starts_guide_engine(self):
        self.assertTrue(await self.module.async_setup_entry(self.hass,self.entry))
        self.assertIn('get_saved_programmes',self.registry)
        self.assertTrue(self.hass.data['tv_guide']['entry'].is_original)
        self.assertTrue(Scheduler.instances[0].scheduled)
        self.assertTrue(await self.module.async_unload_entry(self.hass,self.entry))
        self.assertTrue(Scheduler.instances[0].stopped)
        self.assertEqual(self.hass.data['tv_guide_saved'],{})
        self.assertEqual(self.registry,set())
        for callback in self.entry.callbacks:
            callback()  # Home Assistant processes these after success.
        self.assertTrue(self.entry.listener_removed)

    async def test_failed_platform_setup_unloads_partial_entities_and_runtime(self):
        self.hass.config_entries.fail = RuntimeError('partial platform failure')
        with self.assertRaises(RuntimeError):
            await self.module.async_setup_entry(self.hass,self.entry)
        self.assertEqual(self.hass.config_entries.unloaded,['entry'])
        self.assertTrue(Scheduler.instances[0].stopped)
        self.assertEqual(self.hass.data['tv_guide_saved'],{})
        self.assertEqual(self.registry,set())

    async def test_cancelled_setup_rolls_back_resources(self):
        self.hass.config_entries.fail = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await self.module.async_setup_entry(self.hass,self.entry)
        self.assertTrue(Scheduler.instances[0].stopped)
        self.assertEqual(self.hass.config_entries.unloaded,['entry'])
        self.assertEqual(self.hass.data['tv_guide_saved'],{})

    async def test_first_feed_failure_does_not_forward_or_install_timers(self):
        self.entry.data = {'feed_url':'https://example.org/feed.xml'}
        Coordinator.fail = True
        with self.assertRaises(RuntimeError):
            await self.module.async_setup_entry(self.hass,self.entry)
        self.assertEqual(self.hass.config_entries.forwarded,[])
        self.assertEqual(Scheduler.instances,[])
        self.assertEqual(self.registry,set())

    async def test_failed_unload_retains_live_runtime(self):
        await self.module.async_setup_entry(self.hass,self.entry)
        self.hass.config_entries.unload_ok = False
        self.assertFalse(await self.module.async_unload_entry(self.hass,self.entry))
        self.assertFalse(Scheduler.instances[0].stopped)
        self.assertIn('entry',self.hass.data['tv_guide_saved'])
        self.assertIn('save_bookmark',self.registry)

    async def test_sender_options_notify_calendar_without_feed_reload(self):
        self.entry.data = {'feed_url':'https://example.org/feed.xml','country':'de'}
        await self.module.async_setup_entry(self.hass,self.entry)
        coordinator = self.hass.data['tv_guide']['entry']
        self.entry.options = {'channels':['zdf'],'notification_service':'notify.test'}
        await self.module.async_update_options(self.hass,self.entry)
        self.assertEqual(coordinator.updates,1)
        self.assertEqual(self.hass.config_entries.reloaded,[])
        self.assertEqual(Scheduler.instances[0].notification_service,'notify.test')
        self.entry.options['feed_url']='https://example.org/new.xml'
        await self.module.async_update_options(self.hass,self.entry)
        self.assertEqual(self.hass.config_entries.reloaded,['entry'])

if __name__ == '__main__':
    unittest.main()
