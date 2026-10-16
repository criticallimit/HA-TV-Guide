"""Read the integration's indexed local logo archives from its own storage."""
import base64
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
import threading
import zipfile
from urllib.parse import quote


class LogoLibrary:
    """Read only indexed artwork; downloading is owned by the separate logo worker."""

    def __init__(self, root=None):
        self.root=Path(root) if root is not None else Path(__file__).parent/'logo_library'
        self.archive_root = self.root
        self._lock = threading.RLock()
        self._bundled_index = json.loads((self.root/'index.json').read_text(encoding='utf-8'))
        self.bundled_revision = self._bundled_index['revision']
        self.activate(self._bundled_index, self.root)

    @staticmethod
    def validate_index(index):
        if (not isinstance(index, dict) or index.get('schema_version') != 1
                or not re.fullmatch(r'[0-9a-f]{16,64}', str(index.get('revision', '')))):
            raise ValueError('Invalid logo index')
        entries = index.get('entries')
        if not isinstance(entries, dict) or not 0 < len(entries) <= 100000:
            raise ValueError('Invalid logo entries')
        for source, item in entries.items():
            if (not isinstance(source, str) or len(source) > 512 or not source.startswith('logos/')
                    or '..' in PurePosixPath(source).parts or not isinstance(item, dict)
                    or not re.fullmatch(r'logos-\d{3}\.zip', str(item.get('archive', '')))
                    or not re.fullmatch(r'[0-9a-f]{64}', str(item.get('member', '')))
                    or not re.fullmatch(r'[0-9a-f]{64}', str(item.get('sha256', '')))
                    or item.get('mime') not in {'image/png', 'image/svg+xml', 'image/jpeg', 'image/webp', 'image/gif'}):
                raise ValueError('Invalid logo entry')

        channels = index.get('channels', {})
        if not isinstance(channels, dict) or len(channels) > 5000:
            raise ValueError('Invalid channel logo mappings')
        for key, themes in channels.items():
            if (not isinstance(key, str) or not re.fullmatch(r'[a-z]{2}:[a-zA-Z0-9_-]{1,128}', key)
                    or not isinstance(themes, dict) or set(themes) != {'light', 'dark'}
                    or any(not isinstance(source, str) or source not in entries for source in themes.values())):
                raise ValueError('Invalid channel logo mapping')

    def channel_urls(self, country, channel_id):
        """Return revisioned URLs for main-channel artwork from the active database."""
        with self._lock:
            themes = self.channels.get(f'{country}:{channel_id}', {})
            return {'logo_normalized_' + theme: '/tv_guide/logo/' + quote(source, safe='/') + '?v=' + self.revision
                    for theme, source in themes.items()}

    def activate(self, index, archive_root, manifest=None):
        """Switch the entire verified library while image readers retain a consistent view."""
        self.validate_index(index)
        with self._lock:
            self.entries = index['entries']
            self.channels = index.get('channels', {})
            self.revision = index['revision']
            self.archive_root = Path(archive_root)
            self.download_manifest = manifest
            # The bundled fallback stays on disk; retain only the active index
            # once an independently published library has been activated.
            self._bundled_index = index if self.revision == self.bundled_revision else None
            self._render_cached.cache_clear()

    def contains(self, source):
        with self._lock:
            return source in self.entries

    def configure_cache(self, path):
        index = self._bundled_index
        if index is None:
            index = json.loads((self.root/'index.json').read_text(encoding='utf-8'))
        self.activate(index, Path(path) / self.bundled_revision)

    def read(self, source):
        with self._lock:
            return self._read(source)

    def _read(self, source):
        item=self.entries.get(source)
        if item is None:
            raise KeyError(source)
        with zipfile.ZipFile(self.archive_root/item['archive']) as archive:
            data=archive.read(item['member'])
        if sha256(data).hexdigest()!=item['sha256']:
            raise ValueError('Damaged bundled logo')
        return data,item['mime']

    def render(self, source, normalize=False):
        """Make referenced Europe artwork self-contained for an HTML img element."""
        with self._lock:
            return self._render_cached(source,normalize)

    @lru_cache(maxsize=128)
    def _render_cached(self, source, normalize):
        data,mime=self.read(source)
        if mime=='image/svg+xml':
            svg=data.decode('utf-8')
            def embed(match):
                reference=match[1]
                if reference.startswith(('data:','http:','https:','#')):
                    return match[0]
                target=posixpath.normpath(posixpath.join(posixpath.dirname(source),reference))
                if not target.startswith('logos/europe/assets/'):
                    raise ValueError('Invalid relative logo image')
                artwork,artwork_mime=self.read(target)
                return 'href="data:'+artwork_mime+';base64,'+base64.b64encode(artwork).decode('ascii')+'"'
            svg=re.sub(r'href="([^\"]+)"',embed,svg)
            data=svg.encode('utf-8')
        if normalize:
            encoded=base64.b64encode(data).decode('ascii')
            data=f'''<svg xmlns="http://www.w3.org/2000/svg" width="260" height="64" viewBox="0 0 260 64">
  <image x="5" y="4" width="250" height="56" preserveAspectRatio="xMidYMid meet"
         href="data:{mime};base64,{encoded}"/>
</svg>
'''.encode('utf-8')
            mime='image/svg+xml'
        return data,mime


@lru_cache(maxsize=1)
def bundled_logo_library():
    """Build the shared read-only index in an executor, once per HA process."""
    return LogoLibrary()
