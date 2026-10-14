"""Offline bounded-download, decompression and dedicated resolver lifecycle tests."""
from contextlib import asynccontextmanager
import gzip
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]/'custom_components'/'tv_guide'
PKG='_tvguide_transport_tests'
pkg=types.ModuleType(PKG);pkg.__path__=[str(ROOT)]
ClientError=type('ClientError',(Exception,),{})
ai=types.ModuleType('aiohttp')
ai.ClientError=ClientError
ai.ClientTimeout=lambda **kwargs: kwargs
ai.ClientSession=object
ai.TCPConnector=object
abc=types.ModuleType('aiohttp.abc');abc.AbstractResolver=object
resolver=types.ModuleType('aiohttp.resolver');resolver.DefaultResolver=object
with patch.dict(sys.modules,{PKG:pkg,'aiohttp':ai,'aiohttp.abc':abc,'aiohttp.resolver':resolver}):
    for name in ('xmltv','feed_url','dns_policy','epg_client','secure_transport'):
        spec=importlib.util.spec_from_file_location(PKG+'.'+name,ROOT/(name+'.py'))
        module=importlib.util.module_from_spec(spec)
        sys.modules[spec.name]=module
        spec.loader.exec_module(module)
    client=sys.modules[PKG+'.epg_client']
    transport=module

class Response:
    def __init__(self,status=200,parts=()):
        self.status=status
        self.parts=parts
        self.content=self
        self.read=False
    def raise_for_status(self):
        if self.status>=400:
            raise ClientError('HTTP error')
    async def iter_chunked(self,size):
        self.read=True
        for part in self.parts:
            yield part

class Session:
    def __init__(self,response):
        self.response=response
        self.options=None
    @asynccontextmanager
    async def get(self,url,**kwargs):
        self.options=kwargs
        yield self.response

class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_download_is_bounded_and_redirects_disabled(self):
        session=Session(Response(parts=[b'one',b'two']))
        self.assertEqual(await client.fetch_programmes(session,'https://example.org/feed.xml'),b'onetwo')
        self.assertFalse(session.options['allow_redirects'])
        with patch.object(client,'MAX_WIRE_BYTES',4):
            with self.assertRaises(ValueError):
                await client.fetch_programmes(session,'https://example.org/feed.xml')

    async def test_redirect_partial_and_http_errors_are_not_parsed(self):
        for status in (204,206,301,302,404,500):
            response=Response(status,parts=[b'not XMLTV'])
            with self.subTest(status=status),self.assertRaises(ConnectionError):
                await client.fetch_programmes(Session(response),'https://example.org/feed.xml')
            self.assertFalse(response.read)

    async def test_unsafe_url_is_rejected_before_get(self):
        session=Session(Response())
        with self.assertRaises(ValueError):
            await client.fetch_programmes(session,'https://127.0.0.1/feed.xml')
        self.assertIsNone(session.options)

    def test_gzip_limit_and_invalid_gzip(self):
        compressed=gzip.compress(b'<tv/>')
        self.assertEqual(client.decompress_feed(compressed),b'<tv/>')
        with patch.object(client,'MAX_XML_SIZE',4):
            with self.assertRaises(ValueError):
                client.decompress_feed(compressed)
        with self.assertRaises((OSError,EOFError)):
            client.decompress_feed(b'\x1f\x8bgarbage')

    async def test_session_and_custom_resolver_close_after_failure(self):
        calls=[]
        class Resolver:
            async def close(self):
                calls.append('resolver_closed')
        class Connector:
            def __init__(self,**kwargs):
                calls.append(kwargs)
            async def close(self):
                calls.append('connector_closed')
        class HTTP:
            def __init__(self,**kwargs):
                calls.append(kwargs)
            async def __aenter__(self):
                return self
            async def __aexit__(self,*args):
                calls.append('session_closed')
        with patch.object(transport,'PublicAddressResolver',Resolver),patch.object(transport,'TCPConnector',Connector),patch.object(transport,'ClientSession',HTTP):
            with self.assertRaises(RuntimeError):
                async with transport.public_epg_session():
                    raise RuntimeError('parse failure')
        self.assertFalse(calls[0]['use_dns_cache'])
        self.assertTrue(calls[0]['ssl'])
        self.assertFalse(calls[1]['trust_env'])
        self.assertFalse(calls[1]['auto_decompress'])
        self.assertEqual(calls[-3:],['session_closed','connector_closed','resolver_closed'])

if __name__=='__main__':
    unittest.main()
