"""Use real async HTTP to verify pooling, streaming and cancellation while blocked."""
import asyncio
import threading
import unittest
from aiohttp import ClientSession, web
from urllib.request import Request
from native_support import module

ProviderBridge=module('provider_bridge').ProviderBridge
ProviderTransport=module('provider_transport').ProviderTransport


class ProviderBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.entered=asyncio.Event();self.release=asyncio.Event()
        self.connections=[];self.validators=[]
        async def page(request):
            self.connections.append(id(request.transport))
            self.validators.append(request.headers.get('If-None-Match'))
            if self.validators[-1]=='"v1"':return web.Response(status=304)
            return web.Response(body=b'programme',headers={'ETag':'"v1"'})
        async def blocked(request):
            response=web.StreamResponse();await response.prepare(request)
            await response.write(b'x');self.entered.set()
            await self.release.wait()
            return response
        async def headers(request):
            self.entered.set();await self.release.wait()
            return web.Response(body=b'late')
        app=web.Application();app.router.add_get('/page',page);app.router.add_get('/blocked',blocked);app.router.add_get('/headers',headers)
        self.runner=web.AppRunner(app);await self.runner.setup()
        site=web.TCPSite(self.runner,'127.0.0.1',0);await site.start()
        self.base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])
        self.session=ClientSession()
        self.bridge=ProviderBridge(self.session,asyncio.get_running_loop())

    async def asyncTearDown(self):
        self.release.set();self.bridge.close()
        await asyncio.sleep(0)
        await self.session.close();await self.runner.cleanup()

    async def test_connection_pool_and_304_body_reuse_together(self):
        transport=ProviderTransport(self.bridge.open)
        def read():
            with transport.open(Request(self.base+'/page')) as response:return response.read(4096)
        self.assertEqual(await asyncio.to_thread(read),b'programme')
        self.assertEqual(await asyncio.to_thread(read),b'programme')
        self.assertEqual(self.validators,[None,'"v1"'])
        self.assertEqual(len(set(self.connections)),1)

    async def test_obsolete_country_cancels_a_read_before_socket_timeout(self):
        stopped=threading.Event();self.bridge.stopped=stopped.is_set
        def read():
            with self.bridge.open(Request(self.base+'/blocked'),timeout=30) as response:
                return response.read(65536)
        pending=asyncio.create_task(asyncio.to_thread(read))
        await asyncio.wait_for(self.entered.wait(),2)
        stopped.set()
        with self.assertRaisesRegex(RuntimeError,'cancelled'):
            await asyncio.wait_for(pending,1)

    async def test_obsolete_country_cancels_while_waiting_for_response_headers(self):
        stopped=threading.Event();self.bridge.stopped=stopped.is_set
        def read():
            with self.bridge.open(Request(self.base+'/headers'),timeout=30) as response:return response.read(4096)
        pending=asyncio.create_task(asyncio.to_thread(read))
        await asyncio.wait_for(self.entered.wait(),2)
        stopped.set()
        with self.assertRaisesRegex(RuntimeError,'cancelled'):
            await asyncio.wait_for(pending,1)

    async def test_unload_cancels_an_active_stream(self):
        def read():
            with self.bridge.open(Request(self.base+'/blocked'),timeout=30) as response:return response.read(65536)
        pending=asyncio.create_task(asyncio.to_thread(read))
        await asyncio.wait_for(self.entered.wait(),2)
        self.bridge.close()
        with self.assertRaisesRegex(RuntimeError,'cancelled'):
            await asyncio.wait_for(pending,1)
