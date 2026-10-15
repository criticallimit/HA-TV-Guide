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
        self.module = module
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

    async def test_settings_commit_returns_before_busy_epg_snapshot(self):
        c = self.coordinator
        c.country = 'de'
        c.backend.request = lambda *args: {'ok':True, 'country':'at'}
        c.backend.state_snapshot = lambda: ([], [], [], {'country':'at', 'last_loaded':None,
            'refresh_running':False, 'source_attempts':[], 'refresh_minutes':360})
        await c._sync_lock.acquire()
        request = asyncio.create_task(c.async_guide_request('settings', 'POST', {'refresh_minutes':360}))
        for _ in range(10):
            await asyncio.sleep(0)
        returned_before_snapshot = request.done()
        country_before_snapshot = c.country
        c._sync_lock.release()
        await request
        await asyncio.gather(*self.tasks)
        self.assertTrue(returned_before_snapshot, 'Saving settings must not wait for EPG snapshot synchronization')
        self.assertEqual(country_before_snapshot, 'at')
        self.assertEqual(c.update_interval.total_seconds(), 360*60)

    async def test_malformed_cached_success_timestamp_does_not_break_setup(self):
        for value in ('invalid','2026-10-14T11:00:00','9999-12-31T23:30:00-01:00',None):
            self.coordinator.backend.state_snapshot=lambda:([],[],[],{'country':'de','last_loaded':value,'refresh_running':False,'source_attempts':[],'refresh_minutes':180})
            await self.coordinator._snapshot()
            self.assertIsNone(self.coordinator.last_successful_refresh)

    async def test_shutdown_waits_for_an_owned_settings_commit(self):
        lock=asyncio.Lock()
        self.hass.data={'tv_guide_settings_lock':lock}
        closed=[]
        self.coordinator.backend.close=lambda:closed.append(True)
        await lock.acquire()
        stop=asyncio.create_task(self.coordinator._async_stop_on_shutdown(None))
        await asyncio.sleep(0)
        pending=not stop.done()
        stopped=self.coordinator._closed
        lock.release()
        await stop
        self.assertTrue(pending)
        self.assertFalse(stopped)
        self.assertEqual(closed,[True])

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

    async def test_concurrent_shutdown_waits_for_single_cleanup(self):
        entered = asyncio.Event()
        release = asyncio.Event()
        calls = []
        async def executor(fn, *args):
            calls.append('close')
            entered.set()
            await release.wait()
            return fn(*args)
        self.coordinator.hass.async_add_executor_job = executor
        self.coordinator.backend.close = lambda: calls.append('closed')
        first = asyncio.create_task(self.coordinator.async_stop())
        await entered.wait()
        second = asyncio.create_task(self.coordinator.async_stop())
        await asyncio.sleep(0)
        self.assertFalse(second.done())
        release.set()
        await asyncio.gather(first, second)
        self.assertEqual(calls, ['close', 'closed'])

    async def test_cancelled_shutdown_waiter_does_not_cancel_cleanup(self):
        entered = asyncio.Event()
        release = asyncio.Event()
        calls = []
        async def executor(fn, *args):
            entered.set()
            await release.wait()
            return fn(*args)
        self.coordinator.hass.async_add_executor_job = executor
        self.coordinator.backend.close = lambda: calls.append('closed')
        first = asyncio.create_task(self.coordinator.async_stop())
        await entered.wait()
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first
        second = asyncio.create_task(self.coordinator.async_stop())
        self.assertFalse(second.done())
        release.set()
        await second
        self.assertEqual(calls, ['closed'])

    async def test_maintenance_timer_checks_freshness_independently_of_snapshots(self):
        calls=[]
        self.coordinator.backend.maintain_caches=lambda:calls.append('check')
        await self.coordinator._async_preload(None)
        self.coordinator.async_set_updated_data([])
        await self.coordinator._async_preload(None)
        self.assertEqual(calls,['check','check'])

    async def test_cancelled_setup_closes_backend_created_after_cancellation(self):
        entered, release = asyncio.Event(), asyncio.Event()
        calls = []
        backend = types.SimpleNamespace(
            runtime=types.SimpleNamespace(STORE=types.SimpleNamespace(
                ensure_fresh_async=lambda: calls.append('refresh'))),
            close=lambda: calls.append('closed'),
        )
        self.hass.config = types.SimpleNamespace(
            language='de', country='DE', time_zone='Europe/Berlin',
            path=lambda *parts: str(Path(*parts)),
        )
        self.coordinator.entry.entry_id = 'entry'
        self.coordinator.backend = None
        def constructor(*args):
            return backend
        async def executor(fn, *args):
            if fn is constructor:
                entered.set()
                await release.wait()
            return fn(*args)
        self.hass.async_add_executor_job = executor
        with patch.object(self.module, 'GuideRuntime', constructor):
            setup = asyncio.create_task(self.coordinator._async_update_data())
            await entered.wait()
            setup.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await setup
            stop = asyncio.create_task(self.coordinator.async_stop())
            await asyncio.sleep(0)
            self.assertFalse(stop.done())
            release.set()
            await stop
        self.assertIs(self.coordinator.backend, backend)
        self.assertEqual(calls, ['closed'])
        self.assertIsNone(self.coordinator._cancel_preload)

    async def test_failed_constructor_does_not_hide_original_setup_error(self):
        self.coordinator.backend = None
        self.hass.config = types.SimpleNamespace(
            language='de', country='DE', time_zone='Europe/Berlin',
            path=lambda *parts: str(Path(*parts)),
        )
        self.coordinator.entry.entry_id = 'entry'
        with patch.object(self.module, 'GuideRuntime', side_effect=ValueError('broken cache')):
            with self.assertRaisesRegex(ValueError, 'broken cache'):
                await self.coordinator._async_update_data()
            await self.coordinator.async_stop()

    async def test_stopped_coordinator_cannot_restart_backend(self):
        self.coordinator.backend.close = lambda: None
        await self.coordinator.async_stop()
        with self.assertRaisesRegex(RuntimeError, 'unloading'):
            await self.coordinator._async_update_data()
