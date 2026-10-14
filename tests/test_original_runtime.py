"""Exercise the copied programme engine without HA, ports or provider requests."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "tv_guide"
PKG = "_tvguide_original_runtime_tests"


class OriginalRuntimeTests(unittest.TestCase):
    def setUp(self):
        package = types.ModuleType(PKG)
        package.__path__ = [str(ROOT)]
        self.imports = patch.dict(sys.modules, {PKG: package})
        self.imports.start()
        self.addCleanup(self.imports.stop)
        spec = importlib.util.spec_from_file_location(PKG + '.original_runtime', ROOT / 'original_runtime.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('TVG_TEST_TMP'))
        self.addCleanup(self.temp.cleanup)
        self.backend = module.OriginalRuntime(Path(self.temp.name)/'entry', {'country':'de'}, {'language':'de','country':'DE'}, lambda:None)
        self.addCleanup(self.backend.close)
        self.runtime = self.backend.runtime
        self.submit = self.runtime.start_background
        self.runtime.start_background = lambda *args, **kwargs: None

    def test_startup_is_isolated_from_addon_paths_and_supervisor(self):
        self.assertTrue(self.runtime.OPTIONS_FILE.is_relative_to(Path(self.temp.name)))
        self.assertEqual(self.runtime.home_assistant_locale()['language'],'de')
        with self.assertRaises(RuntimeError):self.runtime.main()
        with self.assertRaises(RuntimeError):self.runtime._ha_notification({})
        with self.assertRaises(ValueError):self.backend.request('bookmarks','POST',{})

    def test_original_guide_all_countries_picker_and_logos(self):
        guide = self.backend.request('guide','GET')
        self.assertEqual(guide['country'],'de')
        self.assertEqual(guide['main_channel_ids'][0],'ard')
        self.assertIn('/tv_guide/frontend/app/logos/de-ard-light.svg',guide['channels'][0]['logo_normalized_light'])
        picker = self.backend.request('personal-channels','GET')
        self.assertEqual(len(picker['supported_countries']),10)
        self.assertTrue(any(item['id'].startswith('gb:') for item in picker['channels']))
        self.assertTrue(any(item['id'].startswith('at:') for item in picker['channels']))

    def test_multicountry_selection_roundtrip_and_restart(self):
        prefs=self.backend.request('personal-channels','GET')
        keys=[next(ch['id'] for ch in prefs['channels'] if ch['id'].startswith(code+':')) for code in ('de','at','gb')]
        result=self.backend.request('personal-channels','POST',{'order':keys,'countries':['de','at','gb']})
        self.assertEqual(result['order'],keys)
        self.assertEqual(self.backend.request('personal-channels','GET')['order'],keys)
        self.assertTrue(self.runtime.PERSONAL_CHANNELS.path.exists())
        self.assertEqual(self.backend.request('guide','GET')['custom_channel_ids'],keys)

    def test_original_provider_map_artwork_and_merge_engine_are_present(self):
        self.assertGreater(len(self.runtime.OFFICIAL_PROVIDER_BY_CHANNEL),10)
        self.assertTrue(callable(self.runtime.STORE._merge_program_lists))
        self.assertTrue(callable(self.runtime.STORE._parse))
        status=self.backend.request('status','GET')
        self.assertIn('official_metrics',status)
        self.assertIn('coverage_metrics',status)

    def test_original_settings_switch_country_and_persist(self):
        settings=self.backend.request('settings','GET')
        result=self.backend.request('settings','POST',{**settings,'country':'at','max_channels':500})
        self.assertTrue(result['country_changed'])
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
        self.assertEqual(calls, [False])

    def test_periodic_refresh_uses_the_owned_pool(self):
        calls = []
        self.runtime.STORE.refresh = lambda: calls.append(threading.current_thread().name)
        self.backend.refresh_active()
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].startswith('tv-guide-native'))

    def test_corrupt_native_options_do_not_prevent_startup(self):
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


if __name__=='__main__':unittest.main()
