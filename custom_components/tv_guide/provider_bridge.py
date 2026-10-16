"""Stream HA's pooled async HTTP client to synchronous source parsers."""
import asyncio
from email.message import Message
from queue import Empty, Queue
import threading
from urllib.error import HTTPError
from urllib.request import Request

from aiohttp import ClientTimeout


class ProviderBridge:
    def __init__(self, session, loop):
        self.session, self.loop = session, loop
        self.stopped = lambda:False
        self._lock = threading.Lock()
        self._futures = set()
        self._closed = False

    def open(self, request, timeout=45):
        if isinstance(request,str):
            request = Request(request)
        response = StreamResponse(self)
        with self._lock:
            if self._closed:
                raise RuntimeError('TV Guide is unloading')
            future = asyncio.run_coroutine_threadsafe(self._receive(request,response,timeout),self.loop)
            response.future = future
            self._futures.add(future)
        def finished(completed):
            with self._lock:
                self._futures.discard(completed)
        future.add_done_callback(finished)
        while not response.ready.wait(.1):
            response.check()
        response.check()
        if response.error is not None:
            response.close()
            raise response.error
        return response

    async def _receive(self, request, stream, timeout):
        try:
            async with self.session.request(request.get_method(), request.full_url,
                    headers=dict(request.header_items()),data=request.data,
                    timeout=ClientTimeout(total=None,connect=timeout,sock_connect=timeout,sock_read=timeout),auto_decompress=False,
                    allow_redirects=True,max_redirects=10) as response:
                stream.headers = Message()
                for key,value in response.headers.items():
                    stream.headers[key] = value
                stream.status = response.status
                if response.status >= 400 or response.status == 304:
                    raise HTTPError(str(response.url),response.status,response.reason,stream.headers,None)
                stream.ready.set()
                received = 0
                async for chunk in response.content.iter_chunked(65536):
                    received += len(chunk)
                    if received > 100*1024*1024:
                        raise ValueError('Provider response exceeds size limit')
                    while stream.chunks.full():
                        stream.space.clear()
                        if stream.chunks.full():
                            await stream.space.wait()
                    stream.chunks.put_nowait(chunk)
        except asyncio.CancelledError:
            stream.error = RuntimeError('TV Guide request cancelled')
            raise
        except Exception as error:
            stream.error = error if isinstance(error,(OSError,ValueError,RuntimeError)) else OSError(str(error))
        finally:
            stream.done = True
            stream.ready.set()

    def close(self):
        with self._lock:
            self._closed = True
            futures = tuple(self._futures)
        for future in futures:
            future.cancel()


class StreamResponse:
    def __init__(self, bridge):
        self.bridge = bridge
        self.chunks = Queue(maxsize=4)
        self.space = asyncio.Event()
        self.ready = threading.Event()
        self.done = False
        self.error = None
        self.future = None
        self.headers = Message()
        self.status = None
        self._buffer = bytearray()

    def check(self):
        if self.bridge.stopped() or self.bridge._closed:
            self.close()
            raise RuntimeError('TV Guide request cancelled')

    def read(self, size=-1):
        self.check()
        if size == 0:
            return b''
        while size < 0 or len(self._buffer) < size:
            self.check()
            if self.done and self.chunks.empty():
                if self.error is not None:
                    raise self.error
                break
            try:
                chunk = self.chunks.get(timeout=.1)
            except Empty:
                continue
            self.bridge.loop.call_soon_threadsafe(self.space.set)
            self._buffer.extend(chunk)
        count = len(self._buffer) if size < 0 else min(size,len(self._buffer))
        result = bytes(self._buffer[:count])
        del self._buffer[:count]
        return result

    def close(self):
        if self.future is not None and not self.future.done():
            self.future.cancel()

    def __enter__(self):
        self.check()
        return self

    def __exit__(self,*args):
        self.close()
