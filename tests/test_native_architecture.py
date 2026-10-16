"""Native state authority, work priorities and bounded conditional provider IO."""
from email.message import Message
from io import BytesIO
import json
from pathlib import Path
import tempfile
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
