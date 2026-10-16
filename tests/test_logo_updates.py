"""Offline daily checks, delta downloads, atomic activation and restart recovery."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import importlib
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from urllib.error import HTTPError
from unittest.mock import patch
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1] / 'custom_components/tv_guide'
PKG = '_tvguide_logo_update_tests'
pkg = types.ModuleType(PKG)
pkg.__path__ = [str(ROOT)]
sys.modules[PKG] = pkg
updates = importlib.import_module(PKG + '.logo_updates')
assets = importlib.import_module(PKG + '.logo_assets')
download = importlib.import_module(PKG + '.logo_download')
NOW = 1800000000


class Response(BytesIO):
    def __init__(self, data, etag=None):
        super().__init__(data)
        self.status = 200
        self.headers = {'ETag':etag} if etag else {}


def version(revision, changed):
    entries, archives = {}, {}
    for number, value in enumerate((changed, b'<svg xmlns="http://www.w3.org/2000/svg"><text>unchanged</text></svg>')):
        source = 'logos/library/' + str(number) + '.svg'
        digest = sha256(value).hexdigest()
        name = f'logos-{number:03}.zip'
        stream = BytesIO()
        with ZipFile(stream, 'w') as archive:
            archive.writestr(digest, value)
        archives[name] = stream.getvalue()
        entries[source] = {'sha256':digest, 'member':digest, 'archive':name, 'mime':'image/svg+xml'}
    index = {'schema_version':1, 'revision':revision, 'entries':entries}
    data = json.dumps(index).encode()
    descriptor = {'schema_version':1, 'generation':int(revision[0],16)-9, 'revision':revision,
                  'base_url':'https://raw.githubusercontent.com/criticallimit/HA-TV-Guide/' + revision[0] * 40 + '/custom_components/tv_guide/logo_library/',
                  'index':{'size':len(data), 'sha256':sha256(data).hexdigest()},
                  'archives':{name:{'size':len(value), 'sha256':sha256(value).hexdigest()} for name,value in archives.items()}}
    return index, data, descriptor, archives


class LogoUpdateTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.bundled = self.root / 'bundled'
        self.bundled.mkdir()
        self.cache = self.root / 'cache'
        self.old_bytes = b'<svg xmlns="http://www.w3.org/2000/svg"><text>old</text></svg>'
        self.new_bytes = self.old_bytes.replace(b'old', b'new')
        self.old = version('a' * 16, self.old_bytes)
        self.new = version('b' * 16, self.new_bytes)
        (self.bundled / 'index.json').write_bytes(self.old[1])
        (self.bundled / 'downloads.json').write_text(json.dumps(self.old[2]))
        (self.bundled / 'updates.json').write_text(json.dumps(self.old[2]))
        self.library = assets.LogoLibrary(self.bundled)
        self.library.configure_cache(self.cache)
        downloader = download.LogoDownload(self.library)
        downloader.run(lambda:False, lambda request,timeout: Response(self.old[3][request.full_url.rsplit('/',1)[-1]]))
        self.assertTrue(downloader.status()['ready'])
        self.assertEqual(self.library.render('logos/library/0.svg')[0], self.old_bytes)
        self.worker = updates.LogoUpdates(self.library, self.cache)
        self.calls = []
        self.remote = self.new

    def opener(self, request, timeout):
        self.calls.append((request.full_url, dict(request.header_items())))
        self.assertEqual(timeout, 15)
        if request.full_url == updates.UPDATE_URL:
            return Response(json.dumps(self.remote[2]).encode(), '"version"')
        self.assertTrue(request.full_url.startswith(self.remote[2]['base_url']))
        name = request.full_url.rsplit('/',1)[-1]
        return Response(self.remote[1] if name == 'index.json' else self.remote[3][name])

    def check(self, **kwargs):
        return self.worker.check(lambda:False, self.opener, now=NOW, **kwargs)

    def test_delta_download_keeps_old_artwork_until_atomic_switch(self):
        def observe(request, timeout):
            self.assertEqual(self.library.render('logos/library/0.svg')[0], self.old_bytes)
            return self.opener(request, timeout)
        replacement = self.worker.check(lambda:False, observe, now=NOW)
        self.assertTrue(replacement.status()['ready'])
        self.assertEqual(self.library.revision, 'b' * 16)
        self.assertEqual(self.library.render('logos/library/0.svg')[0], self.new_bytes)
        self.assertEqual([url.rsplit('/',1)[-1] for url,_ in self.calls], ['updates.json','index.json','logos-000.zip'])
        self.assertFalse(list(self.cache.rglob('*.part')))
        self.assertEqual(json.loads((self.cache/'active.json').read_text())['revision'], 'b' * 16)

    def test_unchanged_metadata_and_304_are_throttled_across_restarts(self):
        self.remote = self.old
        self.assertIsNone(self.check())
        self.assertEqual(len(self.calls), 1)
        restarted = updates.LogoUpdates(self.library, self.cache)
        self.assertIsNone(restarted.check(lambda:False, lambda *a,**k:self.fail('Repeated daily check'), now=NOW+10))
        def unchanged(request, timeout):
            self.assertEqual(request.get_header('If-none-match'), '"version"')
            raise HTTPError(request.full_url, 304, 'Not modified', {}, BytesIO())
        self.assertIsNone(restarted.check(lambda:False, unchanged, now=NOW+updates.CHECK_INTERVAL))
        self.assertIsNone(restarted.check(lambda:False, lambda *a,**k:self.fail('Repeated 304 check'), now=NOW+updates.CHECK_INTERVAL+1))

    def test_failed_download_preserves_active_library_and_retries_without_bad_etag(self):
        def offline(request, timeout):
            if request.full_url.endswith('logos-000.zip'):
                raise OSError('offline')
            return self.opener(request, timeout)
        self.assertIsNone(self.worker.check(lambda:False, offline, now=NOW))
        self.assertEqual(self.library.render('logos/library/0.svg')[0], self.old_bytes)
        self.assertFalse((self.cache/'active.json').exists())
        self.assertNotIn('etag', json.loads((self.cache/'update-check.json').read_text()))
        self.assertIsNone(self.worker.check(lambda:False, lambda *a,**k:self.fail('Retried before next day'), now=NOW+10))
        self.calls.clear()
        self.assertIsNotNone(self.worker.check(lambda:False, self.opener, now=NOW+updates.CHECK_INTERVAL))
        self.assertEqual([url.rsplit('/',1)[-1] for url,_ in self.calls], ['updates.json','logos-000.zip'])

    def test_installed_revision_is_restored_and_verified_without_network(self):
        self.assertIsNotNone(self.check())
        restored = assets.LogoLibrary(self.bundled)
        restored.configure_cache(self.cache)
        updates.LogoUpdates(restored, self.cache)
        self.assertEqual(restored.revision, self.new[0]['revision'])
        self.assertEqual(restored.render('logos/library/0.svg')[0], self.new_bytes)
        downloader = download.LogoDownload(restored)
        downloader.run(lambda:False, lambda *a,**k:self.fail('Redownloaded installed update'))
        self.assertTrue(downloader.status()['ready'])

    def test_entry_reload_reuses_the_active_update_without_retaining_a_second_index(self):
        self.assertIsNotNone(self.check())
        calls = list(self.calls)
        self.library.configure_cache(self.cache)
        self.assertEqual(self.library.render('logos/library/0.svg')[0], self.old_bytes)
        updates.LogoUpdates(self.library, self.cache)
        self.assertEqual(self.library.render('logos/library/0.svg')[0], self.new_bytes)
        self.assertEqual(self.calls, calls)

    def test_revision_only_update_reuses_all_archives(self):
        self.remote = version('b'*16, self.old_bytes)
        self.assertIsNotNone(self.check())
        self.assertEqual([url.rsplit('/',1)[-1] for url,_ in self.calls], ['updates.json','index.json'])
        self.assertEqual(self.library.revision, 'b'*16)

    def test_bad_metadata_and_index_never_replace_the_current_library(self):
        cases = []
        for mutate in (
            lambda d:d.update(base_url='https://example.org/'),
            lambda d:d.update(revision='../escape'),
            lambda d:d['index'].update(sha256='0'*64),
            lambda d:d['index'].update(size=updates.MAX_INDEX_BYTES+1),
        ):
            descriptor = deepcopy(self.new[2])
            mutate(descriptor)
            cases.append(descriptor)
        for descriptor in cases:
            with self.subTest(descriptor=descriptor):
                self.remote = (self.new[0], self.new[1], descriptor, self.new[3])
                self.assertIsNone(self.check(force=True))
                self.assertEqual(self.library.revision, 'a'*16)
                self.assertEqual(self.library.render('logos/library/0.svg')[0], self.old_bytes)
        huge = lambda *a,**k: Response(b'x'*(updates.MAX_DESCRIPTOR_BYTES+1))
        self.assertIsNone(self.worker.check(lambda:False, huge, force=True, now=NOW))

    def test_valid_archive_hash_with_invalid_member_is_not_activated(self):
        index = deepcopy(self.new[0])
        index['entries']['logos/library/0.svg']['sha256'] = '0'*64
        data = json.dumps(index).encode()
        descriptor = deepcopy(self.new[2])
        descriptor['index'] = {'size':len(data), 'sha256':sha256(data).hexdigest()}
        self.remote = (index, data, descriptor, self.new[3])
        self.assertIsNone(self.check())
        self.assertEqual(self.library.revision, 'a'*16)
        self.assertFalse((self.cache/'active.json').exists())

    def test_unload_during_download_cleans_partial_and_keeps_old_library(self):
        stopped = [False]
        outer = self
        class Interrupted(Response):
            def read(self, size):
                stopped[0] = True
                return super().read(size)
        def opener(request, timeout):
            if request.full_url.endswith('logos-000.zip'):
                return Interrupted(outer.new[3]['logos-000.zip'])
            return self.opener(request, timeout)
        self.assertIsNone(self.worker.check(lambda:stopped[0], opener, now=NOW))
        self.assertEqual(self.library.revision, 'a'*16)
        self.assertFalse((self.cache/'active.json').exists())
        self.assertFalse(list(self.cache.rglob('*.part')))
        self.assertIsNotNone(self.check(force=True))

    def test_missing_active_package_falls_back_and_rechecks_instead_of_stale_304(self):
        self.assertIsNotNone(self.check())
        (self.library.archive_root/'logos-000.zip').unlink()
        restored = assets.LogoLibrary(self.bundled)
        restored.configure_cache(self.cache)
        worker = updates.LogoUpdates(restored, self.cache)
        self.assertEqual(restored.revision, 'a'*16)
        self.calls.clear()
        self.assertIsNotNone(worker.check(lambda:False, self.opener, now=NOW+1))
        self.assertNotIn('If-none-match', self.calls[0][1])
        self.assertEqual(restored.render('logos/library/0.svg')[0], self.new_bytes)

    def test_missing_active_pointer_cannot_leave_the_bundled_fallback_on_stale_etag(self):
        self.assertIsNotNone(self.check())
        (self.cache/'active.json').unlink()
        restored = assets.LogoLibrary(self.bundled)
        restored.configure_cache(self.cache)
        worker = updates.LogoUpdates(restored, self.cache)
        self.calls.clear()
        self.assertIsNotNone(worker.check(lambda:False, self.opener, now=NOW+1))
        self.assertNotIn('If-none-match', self.calls[0][1])
        self.assertEqual(restored.revision, 'b'*16)
        self.assertEqual([url.rsplit('/',1)[-1] for url,_ in self.calls], ['updates.json'])

    def test_newer_bundled_installation_does_not_restore_an_older_update_pointer(self):
        self.assertIsNotNone(self.check())
        index = deepcopy(self.old[0])
        index['revision'] = 'c'*16
        (self.bundled/'index.json').write_text(json.dumps(index))
        (self.bundled/'updates.json').write_text(json.dumps(version('c'*16, self.old_bytes)[2]))
        restored = assets.LogoLibrary(self.bundled)
        restored.configure_cache(self.cache)
        worker = updates.LogoUpdates(restored, self.cache)
        self.assertEqual(restored.revision, 'c'*16)
        self.assertEqual(worker._state, {})
        self.assertIsNone(worker.check(lambda:False, self.opener, now=NOW+1))
        self.assertEqual(restored.revision, 'c'*16)

    def test_an_image_read_and_activation_cannot_mix_revisions(self):
        entered, release, activating = threading.Event(), threading.Event(), threading.Event()
        read = self.library._read
        activate = self.library.activate
        def slow_read(source):
            entered.set()
            self.assertTrue(release.wait(5))
            return read(source)
        def observed_activate(*args):
            activating.set()
            return activate(*args)
        self.library._render_cached.cache_clear()
        with patch.object(self.library, '_read', side_effect=slow_read), \
                patch.object(self.library, 'activate', side_effect=observed_activate), \
                ThreadPoolExecutor(max_workers=2) as pool:
            reader = pool.submit(self.library.render, 'logos/library/0.svg')
            self.assertTrue(entered.wait(2))
            update = pool.submit(self.check)
            try:
                self.assertTrue(activating.wait(2))
                self.assertFalse(update.done())
            finally:
                release.set()
            self.assertEqual(reader.result(timeout=5)[0], self.old_bytes)
            self.assertIsNotNone(update.result(timeout=5))
        self.assertEqual(self.library.render('logos/library/0.svg')[0], self.new_bytes)

    def test_older_remote_descriptor_cannot_downgrade_installed_update_after_restart(self):
        self.assertIsNotNone(self.check())
        restored = assets.LogoLibrary(self.bundled)
        restored.configure_cache(self.cache)
        worker = updates.LogoUpdates(restored, self.cache)
        self.remote = self.old
        self.calls.clear()
        self.assertIsNone(worker.check(lambda:False, self.opener, now=NOW+updates.CHECK_INTERVAL))
        self.assertEqual(restored.revision, 'b'*16)
        self.assertEqual(restored.render('logos/library/0.svg')[0], self.new_bytes)
        self.assertEqual(len(self.calls), 1)

    def test_changed_contents_cannot_reuse_the_installed_revision(self):
        self.remote = deepcopy(self.old)
        descriptor = self.remote[2]
        descriptor['generation'] = 2
        descriptor['index']['sha256'] = '0'*64
        self.assertIsNone(self.check())
        self.assertEqual(self.library.render('logos/library/0.svg')[0], self.old_bytes)
        self.assertNotIn('etag', self.worker._state)

    def test_publisher_can_roll_back_artwork_using_a_newer_generation(self):
        self.assertIsNotNone(self.check())
        self.remote = deepcopy(self.old)
        self.remote[2]['generation'] = 3
        self.assertIsNotNone(self.check(force=True))
        self.assertEqual(self.library.revision, 'a'*16)
        self.assertEqual(self.library.render('logos/library/0.svg')[0], self.old_bytes)
        self.remote = self.new
        self.assertIsNone(self.check(force=True))
        self.assertEqual(self.library.revision, 'a'*16)

    def test_malformed_cached_generation_cannot_block_future_updates(self):
        (self.cache/'update-check.json').write_text(json.dumps({'revision':'a'*16, 'generation':['bad']}))
        worker = updates.LogoUpdates(self.library, self.cache)
        self.assertIsNotNone(worker.check(lambda:False, self.opener, now=NOW))
        self.assertEqual(self.library.revision, 'b'*16)

    def test_invalid_cached_etags_are_not_sent_to_the_update_server(self):
        self.remote = self.old
        for etag in ('\r\nInjected: header', 'x'*513, 'non-ascii-\u2603'):
            with self.subTest(etag=etag):
                (self.cache/'update-check.json').write_text(json.dumps({'revision':'a'*16,'etag':etag}))
                worker = updates.LogoUpdates(self.library, self.cache)
                self.calls.clear()
                self.assertIsNone(worker.check(lambda:False, self.opener, now=NOW))
                self.assertEqual(len(self.calls), 1)
                self.assertNotIn('If-none-match', self.calls[0][1])

    def test_invalid_response_etag_does_not_poison_future_checks(self):
        self.remote = self.old
        def opener(request, timeout):
            return Response(json.dumps(self.remote[2]).encode(), 'invalid\r\nheader')
        self.assertIsNone(self.worker.check(lambda:False, opener, now=NOW))
        self.assertNotIn('etag', self.worker._state)
        self.assertIsNone(self.worker.check(lambda:False, self.opener, now=NOW+updates.CHECK_INTERVAL))
        self.assertNotIn('If-none-match', self.calls[0][1])

    def test_concurrent_check_does_not_open_a_second_connection(self):
        self.worker._lock.acquire()
        try:
            self.assertIsNone(self.check())
            self.assertEqual(self.calls, [])
        finally:
            self.worker._lock.release()

    def test_cleanup_failure_cannot_undo_activation(self):
        old = self.cache / ('d'*16)
        old.mkdir()
        with patch.object(updates.shutil, 'rmtree', side_effect=OSError('busy')):
            replacement = self.check()
        self.assertIsNotNone(replacement)
        self.assertEqual(replacement.base_url, self.new[2]['base_url'])
        self.assertEqual(replacement.library.render('logos/library/0.svg')[0], self.new_bytes)

    def test_pointer_write_failure_preserves_old_library_and_verified_downloads(self):
        write = updates._write_json
        def fail_pointer(path, value):
            if path.name == 'active.json':
                raise OSError('storage unavailable')
            return write(path, value)
        with patch.object(updates, '_write_json', side_effect=fail_pointer):
            self.assertIsNone(self.check())
        self.assertEqual(self.library.render('logos/library/0.svg')[0], self.old_bytes)
        self.calls.clear()
        self.assertIsNotNone(self.check(force=True))
        self.assertEqual([url.rsplit('/',1)[-1] for url,_ in self.calls], ['updates.json'])

    def test_obsolete_versions_are_removed_after_success_not_before(self):
        old = self.cache / ('d'*16)
        old.mkdir()
        (old/'unused').write_bytes(b'old')
        self.assertIsNotNone(self.check())
        self.assertFalse(old.exists())
        self.assertTrue((self.cache/('a'*16)).exists())
        self.assertTrue((self.cache/('b'*16)).exists())
