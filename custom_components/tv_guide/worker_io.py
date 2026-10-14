"""Stop provider network work cooperatively when the native runtime unloads."""

class WorkerResponse:
    def __init__(self, response, is_closed):
        self._response=response
        self._context=response
        self._is_closed=is_closed

    def _check(self):
        if self._is_closed():
            raise RuntimeError('TV Guide is unloading')

    def read(self, *args, **kwargs):
        self._check()
        return self._response.read(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._response, name)

    def __enter__(self):
        if self._is_closed():
            self._context.close()
        self._check()
        self._response=self._context.__enter__()
        return self

    def __exit__(self, *args):
        return self._context.__exit__(*args)


def worker_urlopen(opener, is_closed, *args, **kwargs):
    if is_closed():
        raise RuntimeError('TV Guide is unloading')
    response=opener(*args, **kwargs)
    if is_closed():
        response.close()
        raise RuntimeError('TV Guide is unloading')
    return WorkerResponse(response,is_closed)
