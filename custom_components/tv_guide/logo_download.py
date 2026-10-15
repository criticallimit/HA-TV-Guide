"""Verified, resumable logo packages from the integration's pinned GitHub source."""
from hashlib import sha256
import json
import logging
from pathlib import Path
import re
import threading
from urllib.request import Request, build_opener, HTTPRedirectHandler

_LOGGER = logging.getLogger(__name__)


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class LogoDownload:
    def __init__(self, library):
        self.library = library
        manifest = json.loads((library.root / 'downloads.json').read_text(encoding='utf-8'))
        self.base_url = manifest['base_url']
        if not re.fullmatch(r'https://raw\.githubusercontent\.com/criticallimit/HA-TV-Guide/[0-9a-f]{40}/custom_components/tv_guide/logo_library/', self.base_url):
            raise ValueError('Invalid logo download source')
        self.packages = manifest['archives']
        if not self.packages:
            raise ValueError('Empty logo package manifest')
        if hasattr(library, 'entries') and set(self.packages) != {item['archive'] for item in library.entries.values()}:
            raise ValueError('Logo index and download manifest differ')
        for name, item in self.packages.items():
            if (not re.fullmatch(r'logos-\d{3}\.zip', name)
                    or not re.fullmatch(r'[0-9a-f]{64}', item['sha256'])
                    or type(item['size']) is not int or not 0 < item['size'] <= 8 * 1024 * 1024):
                raise ValueError('Invalid logo package manifest')
        self._lock = threading.Lock()
        self._running = False
        self._ready = set()
        self._error = None
        self._bytes = 0
        self._verified = {}

    def status(self):
        with self._lock:
            return {'running': self._running, 'ready': len(self._ready) == len(self.packages) and self._error is None and not self._running,
                    'completed': len(self._ready), 'total': len(self.packages),
                    'bytes': self._bytes, 'total_bytes': sum(p['size'] for p in self.packages.values()),
                    'error': self._error}

    def run(self, stopped, opener=None, *, verify=False):
        with self._lock:
            if self._running:
                return
            self._running = True
            self._error = None
            if verify:
                self._verified.clear()
        try:
            opener = opener or build_opener(NoRedirects()).open
            self.library.archive_root.mkdir(parents=True, exist_ok=True)
            for name, item in self.packages.items():
                if stopped():
                    return
                target = self.library.archive_root / name
                try:
                    stat = target.stat()
                except FileNotFoundError:
                    stat = None
                signature = (stat.st_size, stat.st_mtime_ns) if stat else None
                if signature is not None and self._verified.get(name) == signature:
                    continue
                if stat and stat.st_size == item['size'] and sha256(target.read_bytes()).hexdigest() == item['sha256']:
                    self._mark_ready(name)
                    continue
                with self._lock:
                    self._ready.discard(name)
                    self._verified.pop(name, None)
                    self._bytes = sum(self.packages[key]['size'] for key in self._ready)
                temporary = target.with_suffix('.part')
                digest, received = sha256(), 0
                try:
                    request = Request(self.base_url + name, headers={'User-Agent': 'HA-TV-Guide', 'Accept-Encoding': 'identity'})
                    with opener(request, timeout=15) as response, temporary.open('wb') as output:
                        while not stopped():
                            chunk = response.read(65536)
                            if not chunk:
                                break
                            received += len(chunk)
                            if received > item['size']:
                                raise ValueError('Logo package exceeds expected size')
                            digest.update(chunk)
                            output.write(chunk)
                    if stopped():
                        return
                    if received != item['size'] or digest.hexdigest() != item['sha256']:
                        raise ValueError('Logo package checksum mismatch')
                    temporary.replace(target)
                    self._mark_ready(name)
                finally:
                    temporary.unlink(missing_ok=True)
        except Exception as exc:
            # Keep details out of the UI; retry does not discard verified packages.
            with self._lock:
                self._error = 'download_failed'
            _LOGGER.warning('TV Guide logo download failed: %s', exc)
        finally:
            with self._lock:
                self._running = False

    def _mark_ready(self, name):
        stat = (self.library.archive_root / name).stat()
        with self._lock:
            self._ready.add(name)
            self._verified[name] = (stat.st_size, stat.st_mtime_ns)
            self._bytes = sum(self.packages[key]['size'] for key in self._ready)
