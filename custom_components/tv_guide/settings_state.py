"""One entry-owned settings state; HA owns persistence in native installations."""
import threading
from .original_backend.json_files import read_json_file, write_json_file


class SettingsState:
    def __init__(self, path, options, *, persistent=True):
        self.path = path
        self.persistent = persistent
        self._lock = threading.RLock()
        values = {**(read_json_file(path, {}) if persistent else {}), **options}
        values.pop('backend_mode', None)
        self._values = values
        if persistent:
            write_json_file(path, values)

    def read(self, path=None):
        if path is not None and path != self.path:
            return read_json_file(path, {})
        with self._lock:
            return dict(self._values)

    def replace(self, values, path=None):
        if path is not None and path != self.path:
            write_json_file(path, values)
            return
        with self._lock:
            if self.persistent:
                write_json_file(self.path, values)
            self._values = dict(values)
