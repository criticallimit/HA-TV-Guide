"""Bounded workers that choose the currently relevant queued work first."""
from concurrent.futures import Future
import threading


class WorkScheduler:
    def __init__(self, workers, name='tv-guide'):
        self._condition = threading.Condition()
        self._queue = []
        self._closed = False
        self._sequence = 0
        self._threads = [threading.Thread(target=self._run, name=f'{name}-{i}') for i in range(workers)]
        started = []
        try:
            for thread in self._threads:
                thread.start()
                started.append(thread)
        except BaseException:
            with self._condition:
                self._closed = True
                self._condition.notify_all()
            for thread in started:
                thread.join()
            raise

    def submit(self, function, *args, priority=None, **kwargs):
        future = Future()
        with self._condition:
            if self._closed:
                raise RuntimeError('Scheduler is closed')
            self._sequence += 1
            self._queue.append((priority or (lambda:10), self._sequence, future, function, args, kwargs))
            self._condition.notify()
        return future

    def _run(self):
        while True:
            with self._condition:
                self._condition.wait_for(lambda:self._queue or self._closed)
                if not self._queue:
                    return
                index = min(range(len(self._queue)), key=lambda i:(self._queue[i][0](),self._queue[i][1]))
                _, _, future, function, args, kwargs = self._queue.pop(index)
            if not future.set_running_or_notify_cancel():
                continue
            try:
                result = function(*args, **kwargs)
            except BaseException as error:
                future.set_exception(error)
            else:
                future.set_result(result)

    def shutdown(self, wait=True, *, cancel_futures=False):
        with self._condition:
            self._closed = True
            queued = list(self._queue) if cancel_futures else []
            if cancel_futures:
                self._queue.clear()
            self._condition.notify_all()
        # Callbacks may acquire runtime locks: never execute them under our queue lock.
        for _, _, future, *_ in queued:
            future.cancel()
        if wait:
            for thread in self._threads:
                if thread is not threading.current_thread():
                    thread.join()
