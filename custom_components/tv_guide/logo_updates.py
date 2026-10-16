"""Daily, conditional logo updates with staged downloads and atomic activation."""
from hashlib import sha256
import json
import logging
import os
from pathlib import Path
import re
import shutil
import threading
import time
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, build_opener
from zipfile import ZipFile

from .logo_assets import LogoLibrary
from .logo_download import LogoDownload, NoRedirects, validate_manifest

_LOGGER = logging.getLogger(__name__)
UPDATE_URL = 'https://raw.githubusercontent.com/criticallimit/HA-TV-Guide/main/custom_components/tv_guide/logo_library/updates.json'
CHECK_INTERVAL = 24 * 60 * 60
MAX_DESCRIPTOR_BYTES = 32768
MAX_INDEX_BYTES = 16 * 1024 * 1024


def validate_descriptor(value):
    validate_manifest(value)
    index = value.get('index')
    if (value.get('schema_version') != 1
            or type(value.get('generation')) is not int or not 0 < value['generation'] < 2**53
            or not re.fullmatch(r'[0-9a-f]{16,64}', str(value.get('revision', '')))
            or not isinstance(index, dict)
            or type(index.get('size')) is not int or not 0 < index['size'] <= MAX_INDEX_BYTES
            or not re.fullmatch(r'[0-9a-f]{64}', str(index.get('sha256', '')))):
        raise ValueError('Invalid logo update descriptor')


def _valid_etag(value):
    """Only retain bounded printable HTTP header values from disk or responses."""
    return isinstance(value, str) and 0 < len(value) <= 512 and all(32 <= ord(char) < 127 for char in value)


def _write_json(path, value):
    temporary = path.with_suffix('.tmp')
    try:
        temporary.write_text(json.dumps(value), encoding='utf-8')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_json(path):
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, UnicodeError):
        return {}


class LogoUpdates:
    def __init__(self, library, cache_root):
        self.library = library
        self.root = Path(cache_root)
        self._lock = threading.Lock()
        self._state = _read_json(self.root / 'update-check.json')
        generation = self._state.get('generation', 0)
        if type(generation) is not int or not 0 <= generation < 2**53:
            self._state.pop('generation', None)
        if not _valid_etag(self._state.get('etag')):
            self._state.pop('etag', None)
        self._bundled = _read_json(library.root / 'updates.json')
        self._restore()
        if self._state and self._state.get('revision') != self.library.revision:
            self._state = {}

    def _restore(self):
        active = _read_json(self.root / 'active.json')
        if not active:
            return
        try:
            revision = active['revision']
            if not re.fullmatch(r'[0-9a-f]{16,64}', revision):
                raise ValueError('Invalid active logo revision')
            folder = self.root / revision
            descriptor = _read_json(folder / 'downloads.json')
            validate_descriptor(descriptor)
            if descriptor['generation'] < self._bundled.get('generation', 0):
                raise ValueError('Installed logo update predates the bundled library')
            with (folder / 'index.json').open('rb') as source:
                index = self._index(descriptor, source.read(descriptor['index']['size'] + 1))
            if revision != descriptor['revision']:
                raise ValueError('Invalid active logo revision')
            if any((folder / name).stat().st_size != item['size'] for name, item in descriptor['archives'].items()):
                raise ValueError('Incomplete active logo packages')
            self.library.activate(index, folder, descriptor)
        except (OSError, ValueError, TypeError, KeyError):
            # Keep the bundled fallback, and recheck rather than trusting an ETag
            # belonging to a missing or incompatible installed revision.
            self._discard_active()
            _LOGGER.warning('TV Guide will restore its logo update in the background')

    def _discard_active(self):
        self._state = {}
        try:
            (self.root / 'active.json').unlink(missing_ok=True)
        except OSError:
            pass

    @staticmethod
    def _index(descriptor, data):
        if len(data) != descriptor['index']['size'] or sha256(data).hexdigest() != descriptor['index']['sha256']:
            raise ValueError('Logo index checksum mismatch')
        index = json.loads(data)
        LogoLibrary.validate_index(index)
        if index['revision'] != descriptor['revision']:
            raise ValueError('Logo index revision mismatch')
        validate_manifest(descriptor, index['entries'])
        return index

    @staticmethod
    def _fetch(opener, url, limit, headers=None):
        request = Request(url, headers={'User-Agent':'HA-TV-Guide', 'Accept-Encoding':'identity', **(headers or {})})
        with opener(request, timeout=15) as response:
            status = getattr(response, 'status', 200)
            if status == 304:
                return None, response.headers.get('ETag')
            if status != 200:
                raise ValueError('Incomplete logo metadata response')
            data = response.read(limit + 1)
            if len(data) > limit:
                raise ValueError('Logo metadata exceeds size limit')
            return data, getattr(response, 'headers', {}).get('ETag')

    def check(self, stopped, opener=None, *, force=False, now=None):
        """Return a verified replacement downloader, or None; never alter a good library on failure."""
        if not self._lock.acquire(blocking=False):
            return None
        try:
            now = time.time() if now is None else now
            checked = self._state.get('checked_at')
            if stopped() or (not force and type(checked) in (int, float)
                             and now - CHECK_INTERVAL < checked <= now):
                return None
            self._state['checked_at'] = now
            self._state['revision'] = self.library.revision
            try:
                opener = opener or build_opener(NoRedirects()).open
                headers = {'If-None-Match':self._state['etag']} if isinstance(self._state.get('etag'), str) else {}
                try:
                    data, etag = self._fetch(opener, UPDATE_URL, MAX_DESCRIPTOR_BYTES, headers)
                except HTTPError as exc:
                    if exc.code != 304:
                        raise
                    exc.close()
                    data, etag = None, self._state.get('etag')
                if data is None:
                    self._prune()
                    return None
                descriptor = json.loads(data)
                validate_descriptor(descriptor)
                current = self.library.download_manifest or self._bundled
                generation = max(current.get('generation', 0), self._state.get('generation', 0))
                if descriptor['generation'] < generation:
                    return None  # A stale CDN response must never downgrade artwork.
                replacement = None
                if descriptor['revision'] != self.library.revision:
                    if descriptor['generation'] == generation:
                        raise ValueError('Conflicting logo update generation')
                    replacement = self._stage(descriptor, opener, stopped)
                    if replacement is None:
                        return None
                elif current and (descriptor['index'] != current.get('index')
                                  or descriptor['archives'] != current.get('archives')):
                    raise ValueError('Logo contents changed without a new revision')
                self._state['generation'] = descriptor['generation']
                self._prune()
                self._state['revision'] = self.library.revision
                if _valid_etag(etag):
                    self._state['etag'] = etag
                else:
                    self._state.pop('etag', None)
                return replacement
            except Exception as exc:
                _LOGGER.warning('TV Guide logo update deferred; installed logos remain available: %s', exc)
                return None
            finally:
                try:
                    self.root.mkdir(parents=True, exist_ok=True)
                    _write_json(self.root / 'update-check.json', self._state)
                except OSError:
                    _LOGGER.warning('TV Guide could not persist its logo update check time')
        finally:
            self._lock.release()

    def _stage(self, descriptor, opener, stopped):
        if stopped():
            return None
        folder = self.root / descriptor['revision']
        folder.mkdir(parents=True, exist_ok=True)
        try:
            with (folder / 'index.json').open('rb') as source:
                cached = source.read(descriptor['index']['size'] + 1)
            index = self._index(descriptor, cached)
        except (OSError, ValueError, TypeError, KeyError):
            data, _ = self._fetch(opener, descriptor['base_url'] + 'index.json', descriptor['index']['size'])
            index = self._index(descriptor, data)
            (folder / 'index.json').write_bytes(data)
        if stopped():
            return None
        _write_json(folder / 'downloads.json', descriptor)
        current = self.library.download_manifest or _read_json(self.library.root / 'downloads.json')
        # Reuse unchanged archives locally; no archive network request is needed.
        for name, item in descriptor['archives'].items():
            if stopped():
                return None
            target = folder / name
            source = self.library.archive_root / name
            if not target.exists() and current.get('archives', {}).get(name) == item and source.is_file():
                try:
                    os.link(source, target)
                except OSError:
                    shutil.copyfile(source, target)
        candidate = SimpleNamespace(root=folder, archive_root=folder, entries=index['entries'], download_manifest=descriptor)
        downloader = LogoDownload(candidate)
        downloader.run(stopped, opener)
        if stopped() or not downloader.status()['ready']:
            return None
        # Verify index members too, before exposing any of the new packages.
        by_archive = {}
        for item in index['entries'].values():
            by_archive.setdefault(item['archive'], {})[item['member']] = item['sha256']
        decoded_size = 0
        for name, members in by_archive.items():
            if stopped():
                return None
            with ZipFile(folder / name) as archive:
                for member, digest in members.items():
                    size = archive.getinfo(member).file_size
                    decoded_size += size
                    if size > 8 * 1024 * 1024 or decoded_size > 512 * 1024 * 1024:
                        raise ValueError('Decoded logo data exceeds size limit')
                    if sha256(archive.read(member)).hexdigest() != digest:
                        raise ValueError('Logo member checksum mismatch')
        if stopped():
            return None
        _write_json(self.root / 'active.json', {'revision':descriptor['revision'], 'bundled_revision':self.library.bundled_revision})
        self.library.activate(index, folder, descriptor)
        downloader.library = self.library
        return downloader

    def _prune(self):
        # Shared hard links keep unchanged packages cheap. Cleanup failure must
        # never undo successful activation or leave the old downloader in use.
        try:
            for path in self.root.iterdir():
                if (path.is_dir() and re.fullmatch(r'[0-9a-f]{16,64}', path.name)
                        and path.name not in {self.library.revision, self.library.bundled_revision}):
                    shutil.rmtree(path)
        except OSError:
            _LOGGER.warning('TV Guide could not remove an obsolete logo revision')
