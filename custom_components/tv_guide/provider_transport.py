"""Bounded conditional HTTP cache shared by native provider adapters."""
from collections import OrderedDict
from io import BytesIO
import threading
from urllib.error import HTTPError
from urllib.request import Request


def _header(value):
    return isinstance(value,str) and 0 < len(value) <= 512 and all(32 <= ord(c) < 127 for c in value)


class CachedResponse(BytesIO):
    def __init__(self, data, headers):
        super().__init__(data)
        self.headers = headers
        self.status = 200


class RecordingResponse:
    def __init__(self, response, commit, maximum):
        self.response = response
        self._commit = commit
        self._maximum = maximum
        self._chunks = []
        self._size = 0
        self._complete = False

    def __getattr__(self,name):
        return getattr(self.response,name)

    def __enter__(self):
        self.response = self.response.__enter__()
        return self

    def __exit__(self,*args):
        return self.response.__exit__(*args)

    def read(self, size=-1, *args, **kwargs):
        data = self.response.read(size,*args,**kwargs)
        if self._complete:
            return data
        self._size += len(data)
        if self._size > self._maximum:
            self._chunks = []
            self._complete = True
        else:
            self._chunks.append(data)
            if size < 0 or len(data) < size:
                self._complete = True
                self._commit(b''.join(self._chunks),self.response.headers)
                self._chunks = []
        return data


class ProviderTransport:
    def __init__(self, opener, *, maximum_bytes=8*1024*1024, maximum_entry=2*1024*1024):
        self.opener = opener
        self.maximum_bytes = maximum_bytes
        self.maximum_entry = maximum_entry
        self._entries = OrderedDict()
        self._bytes = 0
        self._lock = threading.Lock()

    def open(self, request, **kwargs):
        if isinstance(request,str):
            request = Request(request)
        if request.get_method() != 'GET' or request.data is not None:
            return self.opener(request,**kwargs)
        headers = dict(request.header_items())
        key = (request.full_url,tuple(sorted((k.lower(),v) for k,v in headers.items())))
        with self._lock:
            cached = self._entries.get(key)
            if cached is not None:
                self._entries.move_to_end(key)
        headers = dict(headers)
        if cached is not None:
            for header, source in [('If-None-Match','ETag'),('If-Modified-Since','Last-Modified')]:
                value = cached[1].get(source)
                if _header(value):
                    headers[header] = value
        outgoing = Request(request.full_url,headers=headers,method='GET')
        try:
            response = self.opener(outgoing,**kwargs)
        except HTTPError as error:
            if error.code != 304 or cached is None:
                raise
            error.close()
            return CachedResponse(cached[0],cached[1])
        control = response.headers.get('Cache-Control','').lower()
        cacheable = ('no-store' not in control and response.headers.get('Vary') != '*'
                     and any(_header(response.headers.get(name)) for name in ('ETag','Last-Modified')))
        if not cacheable:
            with self._lock:
                previous = self._entries.pop(key,None)
                if previous is not None:
                    self._bytes -= len(previous[0])
            return response
        def commit(data, response_headers):
            control = response_headers.get('Cache-Control','').lower()
            if ('no-store' in control or response_headers.get('Vary') == '*'
                    or not any(_header(response_headers.get(name)) for name in ('ETag','Last-Modified'))):
                return
            with self._lock:
                previous = self._entries.pop(key,None)
                if previous is not None:
                    self._bytes -= len(previous[0])
                self._entries[key] = (data,response_headers)
                self._bytes += len(data)
                while self._entries and (self._bytes > self.maximum_bytes or len(self._entries) > 128):
                    _, old = self._entries.popitem(last=False)
                    self._bytes -= len(old[0])
        return RecordingResponse(response,commit,self.maximum_entry)
