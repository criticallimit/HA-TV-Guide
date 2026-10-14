"""Country status and worker completion must stay consistent across HA wakes."""
import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]/'custom_components/tv_guide'
PKG='_tvguide_original_coordinator_tests'

class BaseCoordinator:
    def __init__(self,hass,*args,**kwargs):
        self.hass=hass
        self.last_successful_refresh=None
    def _notify_refresh(self):pass
    def async_set_updated_data(self,records):self.data=records

class OriginalCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        pkg=types.ModuleType(PKG);pkg.__path__=[str(ROOT)]
        base=types.ModuleType(PKG+'.coordinator');base.TVGuideEPGCoordinator=BaseCoordinator
        const=types.ModuleType('homeassistant.const');const.EVENT_HOMEASSISTANT_STOP='stop'
        event=types.ModuleType('homeassistant.helpers.event');event.async_track_time_interval=lambda *args:lambda:None
        self.imports=patch.dict(sys.modules,{PKG:pkg,PKG+'.coordinator':base,'homeassistant.const':const,'homeassistant.helpers.event':event})
        self.imports.start();self.addCleanup(self.imports.stop)
        spec=importlib.util.spec_from_file_location(PKG+'.guide_coordinator',ROOT/'guide_coordinator.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.tasks=[]
        def create(coro):
            task=asyncio.create_task(coro);self.tasks.append(task);return task
        async def executor(fn,*args):return fn(*args)
        self.hass=types.SimpleNamespace(async_add_executor_job=executor,async_create_task=create,bus=types.SimpleNamespace(async_listen_once=lambda *args:lambda:None))
        entry=types.SimpleNamespace(async_on_unload=lambda fn:None)
        self.coordinator=module.TVGuideCoordinator(self.hass,entry,{'country':'de'})
        self.coordinator.backend=types.SimpleNamespace()

    async def test_country_switch_clears_previous_success_and_captures_active_status(self):
        c=self.coordinator
        status={'country':'de','last_loaded':'2026-10-14T11:00:00+00:00','refresh_running':False,'source_attempts':[],'refresh_minutes':180}
        c.backend.state_snapshot=lambda:([],[],[],dict(status))
        await c._snapshot()
        self.assertIsNotNone(c.last_successful_refresh)
        status.update(country='at',last_loaded=None,refresh_running=True,refresh_minutes=60)
        await c._snapshot()
        self.assertEqual(c.country,'at')
        self.assertIsNone(c.last_successful_refresh)
        self.assertTrue(c.refresh_running)
        self.assertEqual(c.update_interval.total_seconds(),3600)

    async def test_unchanged_refresh_state_does_not_notify_again(self):
        coordinator = self.coordinator
        notifications = []
        coordinator._notify_refresh = lambda: notifications.append(coordinator.refresh_running)
        status = {'country': 'de', 'last_loaded': None, 'refresh_running': False,
                  'source_attempts': [], 'refresh_minutes': 180}
        coordinator.backend.state_snapshot = lambda: ([], [], [], dict(status))
        await coordinator._snapshot()
        await coordinator._snapshot()
        self.assertEqual(notifications, [False])
        status['refresh_running'] = True
        await coordinator._snapshot()
        self.assertEqual(notifications, [False, True])

    async def test_completion_wake_during_snapshot_is_not_lost(self):
        entered=asyncio.Event();release=asyncio.Event();calls=[]
        async def snapshot():
            calls.append(len(calls))
            if len(calls)==1:
                entered.set();await release.wait()
            return [len(calls)]
        self.coordinator._snapshot=snapshot
        self.coordinator._schedule_sync()
        await entered.wait()
        self.coordinator._schedule_sync()
        release.set()
        await asyncio.gather(*self.tasks)
        self.assertEqual(calls,[0,1])
        self.assertEqual(self.coordinator.data,[2])
        self.assertFalse(self.coordinator._sync_pending)

    async def test_malformed_cached_success_timestamp_does_not_break_setup(self):
        for value in ('invalid','2026-10-14T11:00:00','9999-12-31T23:30:00-01:00',None):
            self.coordinator.backend.state_snapshot=lambda:([],[],[],{'country':'de','last_loaded':value,'refresh_running':False,'source_attempts':[],'refresh_minutes':180})
            await self.coordinator._snapshot()
            self.assertIsNone(self.coordinator.last_successful_refresh)

    async def test_unload_cancels_preload_timer_before_closing_workers(self):
        calls=[]
        c=self.coordinator
        c._cancel_preload=lambda:calls.append('cancel')
        c.backend.close=lambda:calls.append('close')
        await c.async_stop()
        await c.async_stop()
        await c._async_preload(None)
        self.assertEqual(calls,['cancel','close'])
        self.assertIsNone(c._cancel_preload)

    async def test_maintenance_timer_checks_freshness_independently_of_snapshots(self):
        calls=[]
        self.coordinator.backend.maintain_caches=lambda:calls.append('check')
        await self.coordinator._async_preload(None)
        self.coordinator.async_set_updated_data([])
        await self.coordinator._async_preload(None)
        self.assertEqual(calls,['check','check'])
