"""Exercise the copied programme engine without HA, ports or provider requests."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import json
from datetime import datetime,timedelta,timezone
import threading
from concurrent.futures import ThreadPoolExecutor
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "tv_guide"
PKG = "_tvguide_original_runtime_tests"


class GuideRuntimeTests(unittest.TestCase):
    def setUp(self):
        package = types.ModuleType(PKG)
        package.__path__ = [str(ROOT)]
        self.imports = patch.dict(sys.modules, {PKG: package})
        self.imports.start()
        self.addCleanup(self.imports.stop)
        spec = importlib.util.spec_from_file_location(PKG + '.guide_runtime', ROOT / 'guide_runtime.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('TVG_TEST_TMP'))
        self.addCleanup(self.temp.cleanup)
        self.backend = module.GuideRuntime(Path(self.temp.name)/'entry', {'country':'de'}, {'language':'de','country':'DE'}, lambda:None)
        self.addCleanup(self.backend.close)
        self.runtime = self.backend.runtime
        downloading = patch.object(self.backend.logo_download, 'run')
        downloading.start()
        self.addCleanup(downloading.stop)
        self.submit = self.runtime.start_background
        self.runtime.start_background = lambda *args, **kwargs: None

    def test_startup_is_isolated_from_addon_paths_and_supervisor(self):
        self.assertTrue(self.runtime.OPTIONS_FILE.is_relative_to(Path(self.temp.name)))
        self.assertEqual(self.runtime.home_assistant_locale()['language'],'de')
        self.assertFalse(hasattr(self.runtime,'main'))
        self.assertFalse(hasattr(self.runtime,'_ha_notification'))
        self.assertFalse(hasattr(self.runtime,'load_bookmarks'))
        with self.assertRaises(ValueError):self.backend.request('bookmarks','POST',{})

    def test_native_engine_has_no_obsolete_http_or_logo_workers(self):
        for name in ('normalized_logo_path','normalized_logo_data','preload_country_caches_once'):
            self.assertFalse(hasattr(self.runtime,name),name)
        self.assertFalse(hasattr(self.runtime.Handler,'translate_path'))
        self.assertFalse(hasattr(self.runtime.Handler,'send_response'))
        self.assertFalse(hasattr(self.backend,'preload_next'))

    def test_obsolete_mode_is_removed_from_runtime_options_on_restart(self):
        self.runtime.OPTIONS_FILE.write_text(json.dumps({'backend_mode':'old','theme_mode':'light'}),encoding='utf-8')
        self.backend.close()
        replacement=type(self.backend)(self.runtime.OPTIONS_FILE.parent,{'country':'de','backend_mode':'original'},{'language':'de'},lambda:None)
        try:
            options=json.loads(replacement.runtime.OPTIONS_FILE.read_text(encoding='utf-8'))
            self.assertNotIn('backend_mode',options)
            self.assertEqual(options['theme_mode'],'light')
        finally:
            replacement.close()

    def test_runtime_does_not_load_unused_backend_translation_catalogues(self):
        reads = []
        original = Path.read_text
        def read(path, *args, **kwargs):
            if 'www/locales/' in str(path):
                reads.append(str(path))
            return original(path, *args, **kwargs)
        with patch.object(Path, 'read_text', read):
            replacement = type(self.backend)(Path(self.temp.name) / 'other', {'country':'de'}, {'language':'de'}, lambda:None)
        try:
            self.assertEqual(reads, [], 'Native UI translations and notification translations are loaded independently')
        finally:
            replacement.close()

    def test_logo_maintenance_keeps_programme_revision_and_snapshot(self):
        from concurrent.futures import Future
        guide = self.backend.request('guide', 'GET')
        snapshot = self.backend.state_snapshot()
        def immediate(function):
            result = Future()
            try:
                result.set_result(function())
            except Exception as exc:
                result.set_exception(exc)
            return result
        with patch.object(self.backend._pool, 'submit', side_effect=immediate):
            self.backend.start_logo_download().result()
        self.assertEqual(self.backend.request('guide', 'GET', {'known_revision':guide['revision']}),
                         {'unchanged':True, 'revision':guide['revision']})
        self.assertIs(self.backend.state_snapshot()[0], snapshot[0])

    def test_background_logo_activation_updates_main_logos_without_rebuilding_epg(self):
        guide = self.backend.request('guide', 'GET')
        snapshot = self.backend.state_snapshot()
        downloader = self.backend.logo_download
        revision = 'f' * 16
        def activate(*args, **kwargs):
            index = {**self.backend._logos._bundled_index, 'revision':revision}
            self.backend._logos.activate(index, self.backend._logos.archive_root)
            return downloader
        with patch.object(downloader, 'status', return_value={'ready':True}), \
                patch.object(self.backend.logo_updates, 'check', side_effect=activate):
            self.backend._download_logos()
        updated = self.backend.request('guide', 'GET', {'known_revision':guide['revision']})
        self.assertNotIn('unchanged', updated)
        first = updated['channels'][0]
        self.assertIn('/tv_guide/logo/', first['logo_normalized_light'])
        self.assertIn('?v=' + revision, first['logo_normalized_light'])
        self.assertIs(self.backend.state_snapshot()[0], snapshot[0])

    def test_routine_update_check_does_not_reopen_preparation_progress(self):
        self.runtime.STORE.channels[0]['programs'] = [{'title':'cached'}]
        self.backend._jobs[self.backend._download_logos] = {'forced':False}
        with patch.object(self.backend.logo_download, 'status', return_value={'ready':True,'running':False}):
            status = self.backend.preparation_status()
        self.assertTrue(status['complete'])
        self.assertFalse(status['logos']['running'])

    def test_personal_selection_keeps_shared_programme_snapshot(self):
        snapshot = self.backend.state_snapshot()
        order = self.backend.request('personal-channels', 'GET')['order'][:2][::-1]
        self.backend.request('personal-channels', 'POST', {'order':order, 'countries':['de']})
        self.assertIs(self.backend.state_snapshot()[0], snapshot[0],
                      'Changing selection does not change the shared programme records')

    def test_sender_catalogue_resolves_each_logo_pair_once(self):
        with patch.object(self.runtime, 'normalized_logo_urls', wraps=self.runtime.normalized_logo_urls) as logos:
            picker = self.backend.request('personal-channels', 'GET')
        self.assertEqual(logos.call_count, len(picker['channels']))

    def test_coordinator_snapshot_is_reused_until_backend_changes(self):
        first = self.backend.state_snapshot()
        second = self.backend.state_snapshot()
        self.assertIs(first[0], second[0])
        self.assertIs(first[1], second[1])
        self.backend._backend_changed()
        third = self.backend.state_snapshot()
        self.assertIsNot(first[0], third[0])
        settings = self.backend.request('settings', 'GET')
        self.backend.request('settings', 'POST', {**settings, 'language': 'en'})
        fourth = self.backend.state_snapshot()
        self.assertIsNot(third[0], fourth[0])

    def test_known_revision_skips_full_guide_payload(self):
        first = self.backend.request('guide', 'GET')
        revision = first['revision']
        unchanged = self.backend.request('guide', 'GET', {'known_revision': revision})
        self.assertEqual(unchanged, {'unchanged': True, 'revision': revision})
        self.assertNotIn('channels', unchanged)
        self.backend._backend_changed()
        changed = self.backend.request('guide', 'GET', {'known_revision': revision})
        self.assertIn('channels', changed)
        self.assertNotEqual(changed['revision'], revision)

    def test_prepared_guide_reused_and_invalidated(self):
        first = self.backend.request('guide', 'GET')
        self.assertIs(first, self.backend.request('guide', 'GET'))
        self.backend._backend_changed()
        updated = self.backend.request('guide', 'GET')
        self.assertIsNot(updated, first)
        self.assertIs(updated, self.backend.request('guide', 'GET'))
        settings = self.backend.request('settings', 'GET')
        self.backend.request('settings', 'POST', {**settings, 'language': 'en'})
        self.assertIsNot(self.backend.request('guide', 'GET'), updated)

    def test_first_view_is_small_without_truncating_cached_timelines(self):
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        for channel in self.runtime.STORE.channels:
            channel['programs'] = [
                {'title': str(i), 'start': (now+timedelta(minutes=30*i)).isoformat(),
                 'end': (now+timedelta(minutes=30*(i+1))).isoformat(), 'desc': 'Description. '*60}
                for i in range(336)]
        full = self.backend.request('guide', 'GET')
        preview = self.backend.request('guide', 'GET', {
            'preview': True, 'at': now.isoformat(), 'time_zone': 'Europe/Berlin',
            'known_revision': full['revision']})
        self.assertTrue(preview['_preview'])
        self.assertNotIn('unchanged', preview)
        self.assertEqual(preview['main_channel_ids'], full['main_channel_ids'])
        self.assertEqual(preview['custom_channel_ids'], full['custom_channel_ids'])
        self.assertLess(len(json.dumps(preview)), len(json.dumps(full)) / 20)
        self.assertTrue(all(len(ch['programs']) <= 7 for ch in preview['channels']))
        self.assertIs(self.backend.request('guide', 'GET'), full)
        self.assertEqual(len(full['channels'][0]['programs']), 336)
        self.assertNotIn('_preview', full)
        self.assertEqual(preview['channels'][0]['programs'][0], full['channels'][0]['programs'][0])

    def test_original_guide_all_countries_picker_and_logos(self):
        guide = self.backend.request('guide','GET')
        self.assertEqual(guide['country'],'de')
        self.assertEqual(guide['main_channel_ids'][0],'ard')
        self.assertIn('/tv_guide/frontend/app/logos/de-ard-light.svg',guide['channels'][0]['logo_normalized_light'])
        picker = self.backend.request('personal-channels','GET')
        self.assertEqual(len(picker['supported_countries']),10)
        self.assertTrue(any(item['id'].startswith('gb:') for item in picker['channels']))
        self.assertTrue(any(item['id'].startswith('at:') for item in picker['channels']))

    def test_personal_selection_all_countries_survives_restart_and_filters(self):
        picker = self.backend.request('personal-channels', 'GET')
        keys = [next(ch['id'] for ch in picker['channels'] if ch['source_country'] == code)
                for code in self.runtime.COUNTRIES]
        keys = keys[::2] + keys[1::2]
        now = datetime.now(timezone.utc)
        for key in keys:
            country, _, channel_id = key.partition(':')
            store = self.runtime.PERSONAL_CHANNELS.country_store(country)
            channel = next(ch for ch in store.channels if ch['id'] == channel_id)
            channel['programs'] = [{'title': 'Programme ' + key,
                                    'start': (now - timedelta(minutes=10)).isoformat(),
                                    'end': (now + timedelta(hours=1)).isoformat()}]
            store._save_parsed_cache('test')
        # Catalogue filters must never delete selected foreign stations.
        self.backend.request('personal-channels', 'POST', {'order': keys, 'countries': ['de']})
        self.assertEqual(self.backend.request('guide', 'GET')['custom_channel_ids'], keys)
        self.backend.close()
        replacement = type(self.backend)(self.runtime.OPTIONS_FILE.parent, {'country': 'de'}, {'language': 'de'}, lambda: None)
        try:
            replacement.runtime.start_background = lambda *args, **kwargs: None
            restored = replacement.request('personal-channels', 'GET')
            self.assertEqual(restored['order'], keys)
            self.assertEqual(restored['countries'], ['de'])
            guide = replacement.request('guide', 'GET')
            self.assertEqual(guide['custom_channel_ids'], keys)
            selected = {ch['id']: ch for ch in guide['channels']}
            for key in keys:
                self.assertEqual(selected[key]['source_country'], key.partition(':')[0])
                self.assertEqual(selected[key]['programs'][0]['title'], 'Programme ' + key)
            edited = list(reversed(keys[1:]))
            replacement.request('personal-channels', 'POST', {'order': edited, 'countries': []})
            self.assertEqual(replacement.request('guide', 'GET')['custom_channel_ids'], edited)
            replacement.request('personal-channels', 'POST', {'order': [], 'countries': []})
            self.assertEqual(replacement.request('guide', 'GET')['custom_channel_ids'], [])
        finally:
            replacement.close()

    def test_guide_built_during_personal_commit_is_invalidated_after_save(self):
        initial = self.backend.request('personal-channels', 'GET')['order']
        changed = list(reversed(initial[:2]))
        entered, release = threading.Event(), threading.Event()
        original = self.runtime.PERSONAL_CHANNELS.save
        def blocked(*args):
            entered.set()
            release.wait(5)
            return original(*args)
        with patch.object(self.runtime.PERSONAL_CHANNELS, 'save', blocked), ThreadPoolExecutor(max_workers=2) as pool:
            save = pool.submit(self.backend.request, 'personal-channels', 'POST', {'order': changed, 'countries': ['de']})
            self.assertTrue(entered.wait(2))
            try:
                during = self.backend.request('guide', 'GET')
                self.assertEqual(during['custom_channel_ids'], initial)
            finally:
                release.set()
                self.assertTrue(save.result(timeout=5)['ok'])
        result = self.backend.request('guide', 'GET', {'known_revision': during['revision']})
        self.assertNotIn('unchanged', result, 'A pre-commit guide must not mask the committed selection')
        self.assertEqual(result['custom_channel_ids'], changed)

    def test_personal_save_does_not_wait_for_guide_build(self):
        picker = self.backend.request('personal-channels', 'GET')
        keys = [ch['id'] for ch in picker['channels'][:2]][::-1]
        entered, release = threading.Event(), threading.Event()
        original = self.runtime.PERSONAL_CHANNELS.guide
        def blocked(store):
            entered.set()
            release.wait(5)
            return original(store)
        with patch.object(self.runtime.PERSONAL_CHANNELS, 'guide', blocked), ThreadPoolExecutor(max_workers=2) as pool:
            guide = pool.submit(self.backend.request, 'guide', 'GET')
            self.assertTrue(entered.wait(2))
            save = pool.submit(self.backend.request, 'personal-channels', 'POST', {'order': keys, 'countries': ['de']})
            try:
                self.assertTrue(save.result(timeout=1)['ok'])
            finally:
                release.set()
                guide.result(timeout=5)
        self.assertIsNone(self.backend._guide_cache)
        self.assertEqual(self.backend.request('guide', 'GET')['custom_channel_ids'], keys)

    def test_original_provider_map_artwork_and_merge_engine_are_present(self):
        self.assertGreater(len(self.runtime.OFFICIAL_PROVIDER_BY_CHANNEL),10)
        self.assertTrue(callable(self.runtime.STORE._merge_program_lists))
        self.assertTrue(callable(self.runtime.STORE._parse))
        status=self.backend.request('status','GET')
        self.assertIn('official_metrics',status)
        self.assertIn('coverage_metrics',status)

    def test_settings_save_does_not_wait_for_guide_build(self):
        settings=self.backend.request('settings','GET')
        entered,release=threading.Event(),threading.Event()
        original=self.runtime.PERSONAL_CHANNELS.guide
        def blocked(store):
            entered.set()
            release.wait(5)
            return original(store)
        with patch.object(self.runtime.PERSONAL_CHANNELS,'guide',blocked), ThreadPoolExecutor(max_workers=2) as pool:
            guide=pool.submit(self.backend.request,'guide','GET')
            self.assertTrue(entered.wait(2))
            save=pool.submit(self.backend.request,'settings','POST',{**settings,'language':'en'})
            try:
                result=save.result(timeout=1)
            finally:
                release.set()
                guide.result(timeout=5)
            self.assertTrue(result['ok'])
            self.assertEqual(self.backend.request('settings','GET')['language'],'en')
            self.assertIsNone(self.backend._guide_cache, 'A guide built across a settings change must not be cached')

    def test_settings_save_does_not_wait_for_epg_snapshot_build(self):
        settings=self.backend.request('settings','GET')
        entered,release=threading.Event(),threading.Event()
        original=self.backend.snapshot
        def blocked(*args):
            entered.set()
            release.wait(5)
            return original(*args)
        with patch.object(self.backend,'snapshot',blocked), ThreadPoolExecutor(max_workers=2) as pool:
            snapshot=pool.submit(self.backend.state_snapshot)
            self.assertTrue(entered.wait(2))
            save=pool.submit(self.backend.request,'settings','POST',{**settings,'language':'en'})
            try:
                result=save.result(timeout=1)
            finally:
                release.set()
                captured=snapshot.result(timeout=5)
            self.assertTrue(result['ok'])
            self.assertEqual(self.backend.request('settings','GET')['language'],'en')
            self.assertIs(self.backend._snapshot_cache[0],captured[0])

    def test_snapshot_does_not_restore_old_country_after_concurrent_switch(self):
        settings=self.backend.request('settings','GET')
        entered,release=threading.Event(),threading.Event()
        original=self.backend.snapshot
        def blocked(*args):
            entered.set()
            release.wait(5)
            return original(*args)
        with patch.object(self.backend,'snapshot',blocked), ThreadPoolExecutor(max_workers=2) as pool:
            snapshot=pool.submit(self.backend.state_snapshot)
            self.assertTrue(entered.wait(2))
            try:
                self.backend.request('settings','POST',{**settings,'country':'at'})
            finally:
                release.set()
            result=snapshot.result(timeout=5)
        self.assertEqual(result[3]['country'],'at')
        self.assertTrue(all(channel['id'].startswith('at_') for channel in result[1]))

    def test_interval_change_does_not_force_an_epg_redownload(self):
        settings=self.backend.request('settings','GET')
        calls=[]
        self.runtime.start_background=lambda *args,**kwargs:calls.append((args,kwargs))
        result=self.backend.request('settings','POST',{**settings,'refresh_minutes':360})
        self.assertFalse(result['refresh_started'])
        self.assertEqual(calls,[])
        self.assertEqual(self.runtime.STORE.options['refresh_minutes'],360)

    def test_original_settings_switch_country_and_persist(self):
        settings=self.backend.request('settings','GET')
        result=self.backend.request('settings','POST',{**settings,'country':'at','max_channels':500})
        self.assertTrue(result['country_changed'])
        self.assertEqual(result['settings']['country'], 'at')
        self.assertEqual(result['settings']['max_channels'], 500)
        self.assertEqual(self.backend.request('settings','GET')['country'],'at')
        self.assertEqual(self.backend.request('settings','GET')['max_channels'],500)
        self.assertEqual(self.runtime.load_options_ui()['max_channels'],500)

    def test_invalid_routes_and_settings_do_not_write(self):
        with self.assertRaises(ValueError):self.backend.request('../files','GET')
        with self.assertRaises(ValueError):self.backend.request('guide','DELETE')
        settings=self.backend.request('settings','GET')
        with self.assertRaises(ValueError):self.backend.request('settings','POST',{**settings,'country':'invalid'})
        self.assertEqual(self.backend.request('settings','GET')['country'],'de')

    def test_duplicate_refresh_requests_share_one_owned_job(self):
        started = threading.Event()
        release = threading.Event()
        calls = []
        def refresh(force=False):
            calls.append(force)
            started.set()
            self.assertTrue(release.wait(5))
        try:
            first = self.submit(refresh)
            self.assertTrue(started.wait(5))
            self.assertIs(self.submit(refresh, force=True), first)
            self.assertEqual(len(self.backend._jobs), 1)
        finally:
            release.set()
        first.result(timeout=5)
        self.assertEqual(calls, [False, True])

    def test_duplicate_forced_refresh_does_not_repeat_the_same_forced_work(self):
        started,release=threading.Event(),threading.Event()
        calls=[]
        def refresh(force=False):
            calls.append(force);started.set();self.assertTrue(release.wait(5))
        try:
            first=self.submit(refresh,force=True)
            self.assertTrue(started.wait(5))
            self.assertIs(self.submit(refresh,force=True),first)
        finally:release.set()
        first.result(timeout=5)
        self.assertEqual(calls,[True])

    def test_maintenance_checks_active_then_used_caches_without_open_frontend(self):
        inactive=self.runtime.EPGStore('at')
        self.runtime.COUNTRY_STORES['at']=inactive
        calls=[]
        with patch.object(self.runtime.STORE,'ensure_fresh_async',side_effect=lambda:calls.append('de')),patch.object(inactive,'ensure_fresh_async',side_effect=lambda:calls.append('at')):
            self.backend.maintain_caches()
        # An unselected, idle country must not trigger background maintenance.
        self.assertEqual(calls,['de'])
        self.assertNotIn('at',self.runtime.COUNTRY_STORES)

    def test_refresh_after_unload_does_not_report_started(self):
        self.backend.close()
        with self.assertRaises(RuntimeError):self.backend.request('refresh','GET')

    def test_cached_programmes_with_source_failure_do_not_complete_preparation(self):
        self.runtime.STORE.channels[0]['programs']=[{'title':'cached'}]
        self.runtime.STORE.refresh_running=False
        self.runtime.STORE.last_error='all providers offline'
        with patch.object(self.backend.logo_download,'status',return_value={'ready':True}):
            status=self.backend.preparation_status()
            self.assertFalse(status['complete'])
            self.assertTrue(status['programmes']['error'])
            self.assertFalse(self.backend._preparation_marker.exists())
            self.runtime.STORE.last_error=None
            self.assertTrue(self.backend.preparation_status()['complete'])
            self.assertTrue(self.backend._preparation_marker.exists())
            self.assertFalse(self.backend.preparation_status()['first_install'])

    def test_queued_logo_verification_cannot_report_preparation_complete(self):
        self.runtime.STORE.channels[0]['programs']=[{'title':'cached'}]
        self.runtime.STORE.refresh_running=False
        self.backend._jobs[self.backend._download_logos]={'forced':True}
        with patch.object(self.backend.logo_download,'status',return_value={'ready':True,'running':False}):
            status=self.backend.preparation_status()
            self.assertFalse(status['complete'])
            self.assertTrue(status['logos']['running'])
            self.assertFalse(status['logos']['ready'])
        self.backend._jobs.clear()

    def test_foreign_main_logo_uses_its_country_even_when_another_is_active(self):
        channel=self.runtime.COUNTRY_CATALOGS['gb']['channels'][0]
        for logo in self.backend.logo_urls(channel):
            self.assertTrue(logo.startswith('/tv_guide/frontend/app/logos/gb-'),logo)

    def test_damaged_cached_rows_and_metadata_preserve_valid_programmes(self):
        now=datetime.now(timezone.utc)
        valid={'title':'Valid cache','start':(now-timedelta(minutes=10)).isoformat(),'end':(now+timedelta(minutes=50)).isoformat()}
        invalid={'title':'invalid-utc','start':'9999-12-31T23:30:00-01:00','end':'9999-12-31T23:45:00-01:00'}
        channel={**self.runtime.STORE.channels[0],'programs':[valid,invalid,{'title':'broken','start':'invalid','end':valid['end']},{**valid,'start':'2026-10-14T11:00:00'},None]}
        payload={'schema_version':10,'country':'de','channels':[channel],'source_metrics':[{'ok':True},'bad'],'official_metrics':['bad'],'feed_latest_end':'invalid'}
        self.runtime.STORE.parsed_cache_file.write_text(json.dumps(payload),encoding='utf-8')
        restored=self.runtime.EPGStore('de')
        self.assertEqual(restored.channels[0]['programs'],[valid])
        self.assertEqual(restored.source_metrics,[{'ok':True}])
        self.assertIsNone(restored.feed_latest_end)
        self.assertTrue(restored._cache_fresh())

    def test_restored_main_metadata_uses_current_catalogue_and_keeps_programmes(self):
        now = datetime.now(timezone.utc)
        programme = {'title':'Cached programme', 'start':now.isoformat(), 'end':(now+timedelta(hours=1)).isoformat()}
        current = self.runtime.CHANNELS['channels'][0]
        channel = {**current, 'name':'Outdated station', 'order':99999, 'logo_file':'logos/obsolete.svg', 'programs':[programme]}
        self.runtime.STORE.parsed_cache_file.write_text(json.dumps({
            'schema_version':10, 'country':'de', 'channels':[channel], 'source_metrics':[{'ok':True}]
        }), encoding='utf-8')
        restored = self.runtime.EPGStore('de')
        first = restored.channels[0]
        self.assertEqual(first['id'], current['id'])
        for key in ('name', 'order', 'logo_file', 'xmltv_ids'):
            self.assertEqual(first[key], current[key])
        self.assertEqual(first['programs'], [programme])

    def test_invalid_provider_instants_cannot_poison_guide_guide_timelines(self):
        for value in ('99991231233000 -0100','00010101000000 +0100'):
            self.assertIsNone(self.runtime.xmltv_datetime(value))
        now=datetime.now(timezone.utc)
        valid={'title':'Valid','start':now.isoformat(),'end':(now+timedelta(hours=1)).isoformat()}
        invalid={'title':'Invalid','start':'9999-12-31T23:30:00-01:00','end':'9999-12-31T23:45:00-01:00'}
        self.assertEqual(self.runtime.STORE._validate_program_timeline([invalid,valid]),[valid])

    def test_wrong_cached_programme_container_is_replaced_by_empty_guide_data(self):
        channel={**self.runtime.STORE.channels[0],'programs':{'bad':'container'}}
        payload={'schema_version':10,'country':'de','channels':[channel],'source_metrics':[{'ok':True}]}
        self.runtime.STORE.parsed_cache_file.write_text(json.dumps(payload),encoding='utf-8')
        restored=self.runtime.EPGStore('de')
        self.assertFalse(restored.channels[0]['programs'])
        self.assertFalse(restored._cache_fresh())

    def test_periodic_refresh_uses_the_owned_pool(self):
        calls = []
        self.runtime.STORE.refresh = lambda: calls.append(threading.current_thread().name)
        self.backend.refresh_active()
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].startswith('tv-guide'))

    def test_corrupt_guide_options_do_not_prevent_startup(self):
        root = self.runtime.OPTIONS_FILE.parent
        self.backend.close()
        for value in ('{broken', '[]'):
            with self.subTest(value=value):
                (root/'options.json').write_text(value, encoding='utf-8')
                module = type(self.backend)
                replacement = module(root, {'country':'at'}, {'language':'de'}, lambda:None)
                try:
                    self.assertEqual(replacement.request('settings','GET')['country'], 'at')
                    self.assertFalse((root/'options.tmp').exists())
                finally:
                    replacement.close()

    def test_unload_waits_for_running_worker_and_blocks_new_submissions(self):
        started = threading.Event()
        release = threading.Event()
        closing = threading.Event()
        closed = threading.Event()
        def work():
            started.set()
            self.assertTrue(release.wait(5))
        def close():
            closing.set()
            self.backend.close()
            closed.set()
        try:
            job = self.submit(work)
            self.assertTrue(started.wait(5))
            with ThreadPoolExecutor(max_workers=1) as closer:
                future = closer.submit(close)
                self.assertTrue(closing.wait(5))
                self.assertFalse(closed.wait(0.05))
                release.set()
                future.result(timeout=5)
        finally:
            release.set()
        self.assertTrue(job.done())
        self.assertTrue(self.backend.closed)
        self.assertIsNone(self.submit(lambda: self.fail('Must not run after unload')))

    def test_reference_data_is_repaired_on_restart(self):
        path=self.runtime.BASE/'data/countries.json'
        original=path.read_bytes()
        path.write_text('{}',encoding='utf-8')
        self.backend.close()
        replacement=type(self.backend)(self.runtime.OPTIONS_FILE.parent,{'country':'de'},{'language':'de'},lambda:None)
        try:self.assertEqual(path.read_bytes(),original)
        finally:replacement.close()



    def test_state_snapshot_reports_only_active_country_refresh(self):
        inactive=self.runtime.EPGStore('at')
        inactive.refresh_running=True
        self.runtime.COUNTRY_STORES['at']=inactive
        *_,status=self.backend.state_snapshot()
        self.assertEqual(status['country'],'de')
        self.assertFalse(status['refresh_running'])

    def test_every_curated_main_channel_has_both_local_logo_variants(self):
        for country in self.runtime.COUNTRIES:
            catalog=self.runtime.CHANNELS if country=='de' else self.runtime.COUNTRY_CATALOGS[country]
            for channel in catalog['channels']:
                logos=self.backend.logo_urls({**channel,'id':country+':'+channel['id'],'source_channel_id':channel['id']})
                for logo in logos:
                    self.assertTrue(logo.startswith('/tv_guide/frontend/app/logos/'),(country,channel['id']))
                    self.assertTrue((ROOT/'frontend/app/logos'/logo.rsplit('/',1)[1]).is_file())

    def test_additional_channel_uses_packaged_library_without_downloads(self):
        channel_id,definition=next((key,item) for key,item in self.runtime.LOGO_LIBRARY['channels'].items() if key.startswith('epg_') and self.backend._logos.contains(item.get('light')))
        channel={'id':channel_id,'name':definition['name'],'source_country':definition.get('country','de')}
        with patch.object(self.runtime,'urlopen',side_effect=AssertionError('No logo download')):
            logos=self.backend.logo_urls(channel)
        self.assertTrue(all(url.startswith('/tv_guide/logo/') for url in logos),logos)


if __name__=='__main__':unittest.main()
