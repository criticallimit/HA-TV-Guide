"""Native state authority, work priorities and bounded conditional provider IO."""
from email.message import Message
from io import BytesIO
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request

from native_support import module

SettingsState=module('settings_state').SettingsState
WorkScheduler=module('work_scheduler').WorkScheduler
ProviderTransport=module('provider_transport').ProviderTransport


class Response(BytesIO):
    def __init__(self,data=b'programme',**headers):
        super().__init__(data)
        self.headers=Message()
        for key,value in headers.items():self.headers[key]=value


class NativeStateTests(unittest.TestCase):
    def test_ha_configuration_is_authoritative_and_settings_reads_need_no_disk_io(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'options.json'
            path.write_text(json.dumps({'theme_mode':'dark','country':'de'}))
            state=SettingsState(path,{'theme_mode':'light','country':'at'},persistent=False)
            original=path.read_bytes()
            with patch.object(Path,'read_text',side_effect=AssertionError('Settings read touched disk')):
                self.assertEqual(state.read()['country'],'at')
                state.replace({'country':'fr','theme_mode':'auto'})
                self.assertEqual(state.read()['country'],'fr')
            self.assertEqual(path.read_bytes(),original,'HA-managed settings do not create another persistence authority')
            restored=SettingsState(path,{'country':'fr','theme_mode':'auto'},persistent=False)
            self.assertEqual(restored.read(),{'country':'fr','theme_mode':'auto'})

    def test_failed_standalone_write_preserves_committed_state_and_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'options.json'
            state=SettingsState(path,{'country':'de'})
            before=path.read_bytes()
            with self.assertRaises(TypeError):state.replace({'bad':object()})
            self.assertEqual(state.read(),{'country':'de'})
            self.assertEqual(path.read_bytes(),before)


class WorkPriorityTests(unittest.TestCase):
    def test_latest_active_selection_precedes_background_work_without_more_parallelism(self):
        scheduler=WorkScheduler(1)
        entered,release=threading.Event(),threading.Event()
        order=[];current=['a']
        def block():entered.set();release.wait(3)
        first=scheduler.submit(block)
        try:
            self.assertTrue(entered.wait(1))
            a=scheduler.submit(lambda:order.append('a'),priority=lambda:0 if current[0]=='a' else 10)
            logo=scheduler.submit(lambda:order.append('logo'),priority=lambda:20)
            b=scheduler.submit(lambda:order.append('b'),priority=lambda:0 if current[0]=='b' else 10)
            current[0]='b';release.set()
            for future in [first,a,b,logo]:future.result(timeout=2)
            self.assertEqual(order,['b','a','logo'])
        finally:release.set();scheduler.shutdown(cancel_futures=True)

    def test_interpreter_exit_can_run_its_registered_scheduler_cleanup(self):
        code="import sys,atexit;sys.path.insert(0,"+repr(str(Path(__file__).parent))+ ");from native_support import module;scheduler=module('work_scheduler').WorkScheduler(1);atexit.register(scheduler.shutdown)"
        result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_shutdown_cancels_queued_jobs_and_drains_owned_workers(self):
        scheduler=WorkScheduler(1)
        entered,release=threading.Event(),threading.Event()
        first=scheduler.submit(lambda:(entered.set(),release.wait(3)))
        self.assertTrue(entered.wait(1))
        queued=scheduler.submit(lambda:self.fail('Cancelled job ran'))
        scheduler.shutdown(wait=False,cancel_futures=True)
        self.assertTrue(queued.cancelled())
        release.set();first.result(timeout=2);scheduler.shutdown()
        self.assertTrue(all(not thread.is_alive() for thread in scheduler._threads))


class ConditionalProviderTests(unittest.TestCase):
    def test_unchanged_response_reuses_complete_body_with_validator(self):
        calls=[]
        def open(request,**kwargs):
            calls.append(dict(request.header_items()))
            if len(calls)==1:return Response(ETag='"revision-1"')
            self.assertEqual(request.get_header('If-none-match'),'"revision-1"')
            raise HTTPError(request.full_url,304,'Not Modified',{},None)
        transport=ProviderTransport(open)
        for _ in range(2):
            with transport.open(Request('https://example.org/guide')) as response:
                self.assertEqual(response.read(1024),b'programme')
        self.assertEqual(len(calls),2)

    def test_partial_body_never_becomes_a_valid_304_cache(self):
        calls=[]
        def open(request,**kwargs):calls.append(request);return Response(b'abcdef',ETag='"v1"')
        transport=ProviderTransport(open)
        with transport.open(Request('https://example.org/guide')) as response:self.assertEqual(response.read(2),b'ab')
        with transport.open(Request('https://example.org/guide')) as response:response.read()
        self.assertIsNone(calls[1].get_header('If-none-match'))

    def test_cache_is_bounded_and_no_store_removes_previous_body(self):
        responses=[Response(b'1234',ETag='"a"'),Response(b'5678',ETag='"b"'),Response(b'new',**{'Cache-Control':'no-store'})]
        requests=[]
        def open(request,**kwargs):requests.append(request);return responses.pop(0)
        transport=ProviderTransport(open,maximum_bytes=5)
        for url in ('a','b','b'):
            with transport.open(Request('https://example.org/'+url)) as response:response.read()
        self.assertEqual(transport._bytes,0)
        self.assertEqual(len(transport._entries),0)

    def test_different_representation_headers_do_not_share_a_cache_entry(self):
        seen=[]
        def open(request,**kwargs):seen.append(request);return Response(ETag='"a"')
        transport=ProviderTransport(open)
        for accept in ('application/json','text/html'):
            with transport.open(Request('https://example.org/guide',headers={'Accept':accept})) as response:response.read()
        self.assertIsNone(seen[1].get_header('If-none-match'))


    def test_revalidation_updates_validator_and_honours_no_store(self):
        calls=[]
        def open(request,**kwargs):
            calls.append(request)
            if len(calls)==1:return Response(ETag='"v1"')
            headers=Message()
            headers['ETag']='"v2"'
            if len(calls)==3:headers['Cache-Control']='no-store'
            raise HTTPError(request.full_url,304,'Not Modified',headers,None)
        transport=ProviderTransport(open)
        for _ in range(3):
            with transport.open('https://example.org/guide') as response:
                self.assertEqual(response.read(),b'programme')
        self.assertEqual(calls[2].get_header('If-none-match'),'"v2"')
        self.assertEqual(transport._bytes,0)
        self.assertFalse(transport._entries)

    def test_interrupted_or_oversized_replacement_drops_old_validator(self):
        for oversized in (False,True):
            with self.subTest(oversized=oversized):
                calls=[]
                def open(request,**kwargs):
                    calls.append(request)
                    return Response(b'new body' if len(calls)==2 else b'old',ETag='"v1"')
                transport=ProviderTransport(open,maximum_entry=4)
                with transport.open('https://example.org/guide') as response:response.read()
                with transport.open('https://example.org/guide') as response:
                    response.read(-1 if oversized else 1)
                self.assertEqual(transport._bytes,0)
                with transport.open('https://example.org/guide') as response:response.read()
                self.assertIsNone(calls[2].get_header('If-none-match'))

    def test_partial_content_is_never_cached_as_a_complete_representation(self):
        def open(request,**kwargs):
            response=Response(b'fragment',ETag='"v1"')
            response.status=206
            return response
        transport=ProviderTransport(open)
        with transport.open('https://example.org/guide') as response:response.read()
        self.assertFalse(transport._entries)


class LegacyStorageCleanupTests(unittest.TestCase):
    def test_native_cleanup_preserves_user_data_and_never_follows_reference_symlink(self):
        cleanup=module('storage_cleanup').remove_legacy_storage
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'entry';root.mkdir()
            external=Path(folder)/'outside';external.mkdir()
            (external/'keep').write_text('keep')
            (root/'reference').symlink_to(external,target_is_directory=True)
            (root/'options.json').write_text('{}')
            for name in ('tv_guide_personal_channels.json','tv_guide_channel_order.json','preparation-complete.json'):
                (root/name).write_text('preserve')
            cleanup(root,native_settings=True)
            self.assertFalse((root/'options.json').exists())
            self.assertFalse((root/'reference').is_symlink())
            self.assertEqual((external/'keep').read_text(),'keep')
            for name in ('tv_guide_personal_channels.json','tv_guide_channel_order.json','preparation-complete.json'):
                self.assertEqual((root/name).read_text(),'preserve')
            cleanup(root,native_settings=True)

    def test_standalone_settings_file_is_retained(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'options.json';path.write_text('{}')
            module('storage_cleanup').remove_legacy_storage(root,native_settings=False)
            self.assertTrue(path.exists())
